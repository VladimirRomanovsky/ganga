
import Ganga.Utility.logging
logger = Ganga.Utility.logging.getLogger()

from Ganga.GPIDev.Lib.File.File import File
from Ganga.GPIDev.Lib.File.LocalFile import LocalFile

transformDictionary = {}


def __populate():
    if len(transformDictionary) == 0:
        transformDictionary[type(File())] = LocalFile
        # transformDictionary[ ] =
__populate()


def safeTransformFile(input_file):

    this_type = type(input_file)
    if this_type in transformDictionary:
        return transformDictionary[this_type](input_file)

    logger.error("Cannot safely transform file of type: %s" % (this_type))

    return None

def doesFileExist( input_fileName='some.file', input_list = [] ):

    import fnmatch

    have_matched = False
    for fileName in input_list:
        if fnmatch.fnmatch( input_fileName, fileName ):
            have_matched = True
            break

    return have_matched

