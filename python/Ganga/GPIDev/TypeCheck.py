# NOTICE:
# this module is used by config system to configure logging therefore the logger
# requires special handling
# this module must be importable without any side-effect, especially without
# creation of loggers by surrounding packages...

from Ganga.Utility.util import importName
from inspect import isclass

found_types = {}

def _valueTypeAllowed(val, valTypeList, logger=None):
    for _t in valTypeList:

        try:
            from Ganga.GPIDev.Base.Proxy import isType
        except ImportError:
            isType = isinstance

        if _t is None:
            if val is None:
                return True

        if not isType(_t, str) and isclass(_t):
            _type = _t
            _val = val
        else:
            _dotMod = _t.split('.')
            if len(_dotMod) > 1:
                if not hasattr(val, '_proxyClass'):
                    # val is probably a normal Python object.
                    continue
                _type = importName('.'.join(_dotMod[0:-1]), _dotMod[-1])
                _val = val
            else:  # Native Python type
                try:
                    if type(_t) == str:
                        global found_types
                        if not _t in found_types.keys():
                            found_types[_t] = eval(_t)
                        _type = found_types[_t]
                        _type = eval(_t)  # '_type' is actually the class name
                    else:
                        _type = _t
                except NameError:
                    logger.error("Invalid native Python type: '%s'" % _t)
                    continue
                _val = val

        # Deal with the case where type is None.
        if _type is None:
            if _val is None:
                return True
            else:
                continue
        elif isType(_val, _type):
            return True
    return False
