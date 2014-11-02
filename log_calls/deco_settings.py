__author__ = "Brian O'Neill"  # BTO
__version__ = '0.1.13'
__doc__ = """
DecoSettingsMapping -- class that's usable with any class-based decorator
that has several keyword parameters; this class makes it possible for
a user to access the collection of settings as an attribute
(object of type DecoSettingsMapping) of the decorated function.
The attribute/obj of type DecoSettingsMapping provides
    (*) a mapping interface for the decorator's keyword params
    (*) an attribute interface for its keyword params
        i.e. attributes of the same names,
    as well as 'direct' and 'indirect' values for its keyword params
    q.v.
Using this class, any setting under its management can take two kinds of values:
direct and indirect, which you can think of as static and dynamic respectively.
Direct/static values are actual values used when the decorated function is
interpreted, e.g. enabled=True, args_sep=" / ". Indirect/dynamic values are
strings that name keyword arguments of the decorated function; when the
decorated function is called, the arguments passed by keyword and the
parameters of the decorated function are searched for the named parameter,
and if it is found, its value is used. Parameters whose normal type is str
(args_sep) indicate an indirect value by appending an '='.

Thus, in:
    @log_calls(args_sep='sep=', prefix="MyClass.")
    def f(a, b, c, sep='|'): pass
args_sep has an indirect value, and prefix has a direct value. A call can
dynamically override the default value in the signature of f by supplying
a value:
    f(1, 2, 3, sep=' $ ')
or use func's default by omitting the sep argument.
A decorated function doesn't have to explicitly declare the named parameter,
if its signature includes **kwargs. Consider:
    @log_calls(enabled='enable')
    def func1(a, b, c, **kwargs): pass
    @log_calls(enabled='enable')
    def func2(z, **kwargs): func1(z, z+1, z+2, **kwargs)
When the following statement is executed, the calls to both func1 and func2
will be logged:
    func2(17, enable=True)
whereas neither of the following two statements will trigger logging:
    func2(42, enable=False)
    func2(99)

As a concession to consistency, any parameter value that names a keyword
parameter of the decorated function can also end in a trailing '=', which
is stripped. Thus, enabled='enable_=' indicates an indirect value supplied
by the keyword 'enable_' of the decorated function.
"""
from collections import OrderedDict
import pprint
from .helpers import is_keyword_param

__all__ = ['DecoSetting', 'DecoSettingsMapping']


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# classes
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
class DecoSetting():
    """a little struct - static info about one setting (keyword parameter),
                         sans any value.
    Callers can add additional fields by passing additional keyword args.
    The additional fields/keys & values are made attributes of this object,
    and a (sorted) list of the keys is saved (_user_attrs).
    """
    def __init__(self, name, final_type, default, *,
                 allow_falsy, allow_indirect=True, mutable=True,
                 **more_attributes):
        assert not default or isinstance(default, final_type)
        self.name = name                # key
        self.final_type = final_type    # bool int str logging.Logger ...
        self.default = default
        self.allow_falsy = allow_falsy  # is a falsy final val of setting allowed
        self.allow_indirect = allow_indirect  # are indirect values allowed
        self.mutable = mutable
        # we need write fields in repr the same way every time,
        # so even though more_attributes isn't ordered,
        # we need to pick an order & stick to it
        self._user_attrs = sorted(list(more_attributes))
        self.__dict__.update(more_attributes)

    def __repr__(self):
        #final_type = repr(self.final_type)[8:-2]     # E.g. <class 'int'>  -->  int
        final_type = self.final_type.__name__         # WHY NOT THIS? lol
        #default = self.default if final_type != 'str' else repr(self.default)
        output = ("DecoSetting(%r, %s, %r, allow_falsy=%s, allow_indirect=%s, mutable=%s"
                  %
                  (self.name, final_type, self.default,
                   self.allow_falsy, self.allow_indirect, self.mutable)
        )
        # append user attrs
        for attr in self._user_attrs:
            output += ", %s=%r" % (attr, self.__dict__[attr])

        output += ")"
        return output


class DecoSettingsMapping():
    """Usable with any class-based decorator that wants to implement
    a mapping interface and attribute interface for its keyword params,
    as well as 'direct' and 'indirect' values for its keyword params"""
    # Class-level mapping: classname |-> OrderedDict of class's settings (info 'structs')
    _classname2SettingsData_dict = {}

    # When this is last char of a parameter value (to decorator),
    # interpret value of parameter to be the name of
    # a keyword parameter ** of the wrapped function f **
    KEYWORD_MARKER = '='

    @classmethod
    def register_class_settings(cls, deco_classname, settings_iter):
        """
        Called before __init__, presently - by deco class.
        Client class should call this *** from class level ***
        e.g.
            DecoSettingsMapping.register_class_settings('log_calls', _setting_info_list, descr_names)

        Add item (classname, od) to _classname2SettingsData_dict
        where od is an ordered dict built from items of settings_iter.
        cls: this class
        clsname: key for dict produced from settings_iter
        settings_iter: iterable of Keyed"""
        od = OrderedDict()
        for setting in settings_iter:
            od[setting.name] = setting

        cls._classname2SettingsData_dict[deco_classname] = od

        # <<<attributes>>> Set up descriptors
        for name in od:
            setattr(cls, name, cls.make_setting_descriptor(name))

    # <<<attributes>>>
    @classmethod
    def make_setting_descriptor(cls, name):
        class SettingDescr():
            """A little data descriptor which just delegates
            to __getitem__ and __setitem__ of instance"""
            def __get__(self, instance, owner):
                """
                instance: a DecoSettingsMapping
                owner: class DecoSettingsMapping(?)"""
                return instance[name]

            def __set__(self, instance, value):
                """
                instance: a DecoSettingsMapping
                value: what to set"""
                # ONLY do this is name is a legit setting name
                # (for this obj, as per this obj's initialization)
                instance[name] = value

        return SettingDescr()

    @property
    def _deco_class_settings_dict(self):
        """Can't use/call till self.deco_class set in __init__"""
        return self._classname2SettingsData_dict[self.deco_class.__name__]

    def __init__(self, *, deco_class, **values_dict):
        """classname: name of class that has already stored its settings
        by calling register_class_settings(cls, classname, settings_iter)

        values_iterable: iterable of pairs
                       (name,
                        value such as is passed to log_calls-__init__)
                        values are either 'direct' or 'indirect'

        Assumption: every name in values_iterable is info.name
                    for some info in settings_info.
        Must be called after __init__ sets self.classname."""

        self.deco_class = deco_class
        class_settings_dict = self._deco_class_settings_dict

        # Insert values in the proper order - as given by caller
        self._tagged_values_dict = OrderedDict()    # stores pairs inserted by __setitem__
        for k in self._deco_class_settings_dict:
            if k in values_dict:                    # allow k to be set later
                self.__setitem__(k, values_dict[k],
                                 _class_settings_dict_=class_settings_dict)

    def registered_class_settings_repr(self):
        list_of_settingsinfo_reprs = []

        for k, info in self._deco_class_settings_dict.items():
            list_of_settingsinfo_reprs.append(repr(info))

        return ("DecoSettingsMapping.register_class_settings([\n"
                "    %s\n"
                "])") % ',\n    '.join(list_of_settingsinfo_reprs)

    def __setitem__(self, key, value, _class_settings_dict_=None, _force_mutable=False):
        """
        key: name of setting, e.g. 'prefix';
             must be in self._deco_class_settings_dict()
        value: something passed to __init__ (of log_calls),
        _class_settings_dict_: passed by __init__ or any other method that will
                               call many times, saves this method from having
                               to do self._deco_class_settings_dict() on each call
        _force_mutable: if key is already in self._tagged_values_dict and
                        it's not mutable, attempting to __setitem__ on it
                        raises KeyError, unless force_mutable is True
                        in which case it will be written.
        Store pair (is_indirect, modded_val) at key in self._tagged_values_dict[key]
        where
            is_indirect: bool,
            modded_val = val if kind is direct (not is_indirect),
                       = keyword of wrapped fn if is_indirect
                         (sans any trailing '=')
        THIS method assumes that the values in self._deco_class_settings_dict()
        are DecoSetting objects -- all fields of that class are used
        """
        class_settings_dict = _class_settings_dict_ or self._deco_class_settings_dict
        if key not in class_settings_dict:
            raise KeyError(
                "DecoSettingsMapping.__setitem__: no such setting (key) as '%s'" % key)

        info = class_settings_dict[key]
        final_type = info.final_type
        default = info.default
        allow_falsy = info.default
        allow_indirect = info.allow_indirect

        # if the setting is set-once-only (not mutable),
        # raise AttributeError if it's already set, unless _force_mutable:
        if not info.mutable and not _force_mutable and key in self._tagged_values_dict:
            raise ValueError("%s' is write-once (current value: %r)"
                             % (key, self._tagged_values_dict[key][1]))
        if not allow_indirect:
            self._tagged_values_dict[key] = False, value
            return

        # Detect fixup direct/static values, except for final_type == str
        if not isinstance(value, str) or not value:
            indirect = False
            # value not a str, or == '', so use value as-is if valid, else default
            if (not value and not allow_falsy) or not isinstance(value, final_type):
                value = default
        else:                           # val is a nonempty str
            if final_type != str:       # val designates a keyword of f
                indirect = True
                # Remove trailing self.KEYWORD_MARKER if any
                if value[-1] == self.KEYWORD_MARKER:
                    value = value[:-1]
            else:                       # final_type == str
                # val denotes an f-keyword IFF last char is KEYWORD_MARKER
                indirect = (value[-1] == self.KEYWORD_MARKER)
                if indirect:
                    value = value[:-1]

        self._tagged_values_dict[key] = indirect, value

    def __getitem__(self, key):
        indirect, value = self._tagged_values_dict[key]
        return value + '=' if indirect else value

    def __len__(self):
        return len(self._tagged_values_dict)

    def __iter__(self):
        return (name for name in self._tagged_values_dict)

    def items(self):
        return ((name, self.__getitem__(name)) for name in self._tagged_values_dict)

    def __contains__(self, key):
        return key in self._tagged_values_dict

    def __repr__(self):
        return ("DecoSettingsMapping( \n"
                "    deco_class=%s,\n"
                "    ** %s\n"
                ")") % \
               (self.deco_class.__name__,
                pprint.pformat(self.as_OrderedDict(), indent=8)
               )

    def __str__(self):
        return str(self.as_dict())

    def update(self, *dicts, **d_settings):
        """Do __setitem__ for every key/value pair in every dictionary
        in dicts + (d_settings,).
        Allow but ignore attempts to write to immutable keys!
        This permits the user to get the settings as_dict() or as_OrderedDict(),
        make changes & use them,
        and then restore the original settings, which will contain items
        for immutable settings too. Otherwise the user would have to
        remove all the immutable keys before doing update - ugh.
        """
        for d in dicts + (d_settings,):
            for k, v in d.items():
                # skip immutable settings
                if (k in self._deco_class_settings_dict
                    and not self._deco_class_settings_dict[k].mutable):
                    continue
                # otherwise, do it (whether it's a setting key or not)
                self.__setitem__(k, v, _class_settings_dict_=self._deco_class_settings_dict)

    def as_OrderedDict(self):
        od = OrderedDict()
        for k, v in self._tagged_values_dict.items():
            od[k] = v[1]
        return od

    def as_dict(self):
        return dict(self.as_OrderedDict())

    def _get_tagged_value(self, key):
        """Return (indirect, value) for key"""
        return self._tagged_values_dict[key]

    def get_final_value(self, name, *dicts, fparams):
        """
        name:    key into self._tagged_values_dict, self._setting_info_list
        *dicts:  varargs, usually just kwargs of a call to some function f,
                 but it can also be e.g. *(explicit_kwargs, defaulted_kwargs,
                 implicit_kwargs, with fparams=None) of that function f,
        fparams: inspect.signature(f).parameters of that function f
                 NOTE: it's a mandatory, keyword-ONLY argument
        THIS method assumes that the objs stored in self._deco_class_settings_dict
        are DecoSetting objects -- this method uses every attribute of that class
                                   except allow_indirect.
        A very (deco-)specific method, it seems
        """
        indirect, di_val = self._tagged_values_dict[name]  # di_ - direct or indirect
        if not indirect:
            return di_val

        # di_val designates a (potential) f-keyword

        setting_info = self._deco_class_settings_dict[name]
        final_type = setting_info.final_type
        default = setting_info.default
        allow_falsy = setting_info.allow_falsy

        # If di_val is in any of the dictionaries, get corresponding value
        found = False
        for d in dicts:
            if di_val in d:            # actually passed to f
                val = d[di_val]
                found = True
                break

        if not found:
            if fparams and is_keyword_param(fparams.get(di_val)): # not passed; explicit f-kwd?
                # yes, explicit param of f, so use f's default value
                val = fparams[di_val].default
            else:
                val = default

        # fixup: "loggers" that aren't loggers, "strs" that arent strs, etc
#        if (not val and not allow_falsy) or (val and not isinstance(val, final_type)):
        if (not val and not allow_falsy) or (not isinstance(val, final_type)):
            val = default
        return val
