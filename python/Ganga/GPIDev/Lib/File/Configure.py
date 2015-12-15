
from Ganga.Utility.Config import getConfig

outputconfig = None

if outputconfig is None:
    from Ganga.Utility.Config import makeConfig
    outputconfig = makeConfig(
        "Output", "configuration section for postprocessing the output")

def getSharedPath():
    # Required to be initialized for ShareDir object
    from Ganga.Utility.files import expandfilename
    import os.path
    Conf_config = getConfig('Configuration')
    root_default = os.path.join(expandfilename(Conf_config['gangadir']), 'shared', Conf_config['user'])
    return root_default

def Configure():

    outputconfig.addOption('AutoRemoveFilesWithJob', False,
                           'if True, each outputfile of type in list AutoRemoveFileTypes will be removed when the job is')
    outputconfig.addOption('AutoRemoveFileTypes', [
                           'DiracFile'], 'List of outputfile types that will be auto removed when job is removed if AutoRemoveFilesWithJob is True')

    outputconfig.addOption('PostProcessLocationsFileName', '__postprocesslocations__',
                           'name of the file that will contain the locations of the uploaded from the WN files')

    outputconfig.addOption('FailJobIfNoOutputMatched', True,
                           'if True, a job will be marked failed if output is asked for but not found.')

    outputconfig.addOption('ForbidLegacyOutput', True, 'if True, writing to the job outputdata and outputsandbox fields will be forbidden')

    outputconfig.addOption('ForbidLegacyInput', True, 'if True, writing to the job inputsandbox field will be forbidden')

    docstr_Ext = 'fileExtensions:list of output files that will be written to %s,\
backendPostprocess:defines where postprocessing should be done (WN/client) on different backends,\
uploadOptions:config values needed for the actual %s upload'

    # LocalFile
#    LocalPost = {'Localhost': 'WN', 'Interactive': 'WN', 'CREAM': 'client', 'Dirac': 'client'}
#    
#    LocalUpOpt = {}
#
#    LocalFileExt = docstr_Ext % ('Local', 'Local')
#
#    outputconfig.addOption('LocalFile',
#                            {'fileExtensions': ['*.txt'],
#                             'backendPostprocess' : LocalPost,
#                             'uploadOptions' : LocalUpOpt},
#                            LocalFileExt)


    # LCGSEFILE

    LCGSEBakPost = {'LSF': 'client', 'PBS': 'client', 'LCG': 'WN', 'CREAM': 'WN',
                    'ARC': 'WN', 'Localhost': 'WN', 'Interactive': 'WN'}
    LCGSEUpOpt = {'LFC_HOST': 'lfc-dteam.cern.ch', 'dest_SRM': 'srm-public.cern.ch'}
    LCGSEFileExt = docstr_Ext % ('LCG SE', 'LCG')

    outputconfig.addOption('LCGSEFile',
                           {'fileExtensions': ['*.root', '*.asd'],
                            'backendPostprocess': LCGSEBakPost,
                            'uploadOptions': LCGSEUpOpt},
                           LCGSEFileExt)

    # DiracFile

    # Should this be in Core or elsewhere?
    diracBackPost = {'Dirac': 'WN', 'LSF': 'WN', 'PBS': 'WN', 'LCG': 'WN',
                     'CREAM': 'WN', 'ARC': 'WN', 'Localhost': 'WN', 'Interactive': 'WN'}
    diracFileExts = docstr_Ext % ('DIRAC', 'DIRAC')

    outputconfig.addOption('DiracFile',
                           {'fileExtensions': ['*.dst'],
                            'backendPostprocess': diracBackPost,
                            'uploadOptions': {},
                            'defaultSite': {'upload': 'CERN-USER', 'download': 'CERN-USER'}},
                           diracFileExts)

    # GoogleFile

    GoogleFileBackPost = {'Dirac': 'client', 'LSF': 'client', 'PBS': 'client', 'LCG': 'client',
                          'CREAM': 'client', 'ARC': 'client', 'Localhost': 'client', 'Interactive': 'client'}
    GoogleFileExts = docstr_Ext % ('GoogleDrive', 'Google')

    outputconfig.addOption('GoogleFile',
                           {'fileExtensions': [],
                            'backendPostprocess': GoogleFileBackPost,
                            'uploadOptions': {}},
                           GoogleFileExts)

    # MassStorageFile

    import pwd
    import grp
    Conf_config = getConfig('Configuration')
    if 'user' in Conf_config:
        user = Conf_config ['user']
    else:
        #import sys
        #sys.stderr.write('Configure Error: %s' % str(err) )
        import getpass
        user = getpass.getuser()


    ## FIXME Sometimes the wrong user is set gere for the unittests, I've added this to correct for it - rcurrie
    try:
        pwd_nam = pwd.getpwnam(user)
    except:
        import getpass
        user = getpass.getuser()
        pwd_nam = pwd.getpwnam(user)

    groupid = grp.getgrgid(pwd_nam.pw_gid).gr_name
    groupnames = {'z5': 'lhcb', 'zp': 'atlas', 'zh': 'cms', 'vl': 'na62'}
    groupname = groupnames.get(groupid, 'undefined')

    try:
        import os.path
        massStoragePath = os.path.join(os.environ['EOS_HOME'], 'ganga')
    except KeyError:
        massStoragePath = "/eos/%s/user/%s/%s/ganga" % (
            groupname, user[0], user)

    # From:
    # http://eos.cern.ch/index.php?option=com_content&view=article&id=87:using-eos-at-cern&catid=31:general&Itemid=41
    protoByExperiment = {'atlas': 'root://eosatlas.cern.ch',
                         'cms': 'root://eocms.cern.ch',
                         'lhcb': 'root://eoslhcb.cern.ch',
                         'alice': 'root://eosalice.cern.ch',
                         # These last 2 are guesses based on the standard
                         'na62': 'root://eosna62.cern.ch',
                         'undefined': 'root://eos.cern.ch'}
    defaultMassStorageProto = protoByExperiment[groupname]

    prefix = '/afs/cern.ch/project/eos/installation/%s/bin/eos.select ' % groupname
    massStorageUploadOptions = {'mkdir_cmd': prefix + 'mkdir', 'cp_cmd':
                                prefix + 'cp', 'ls_cmd': prefix + 'ls', 'path': massStoragePath}

    massStorageFileExt = docstr_Ext % ('Mass Storage', 'EOS')

    massStorageBackendPost = {'LSF': 'WN', 'PBS': 'WN', 'LCG': 'client', 'CREAM': 'client',
                              'ARC': 'client', 'Localhost': 'WN', 'Interactive': 'client', 'Dirac': 'client'}

    outputconfig.addOption('MassStorageFile',
                           {'fileExtensions': [''],
                            'backendPostprocess': massStorageBackendPost,
                            'uploadOptions': massStorageUploadOptions,
                            'defaultProtocol': defaultMassStorageProto},
                           massStorageFileExt)

Configure()

