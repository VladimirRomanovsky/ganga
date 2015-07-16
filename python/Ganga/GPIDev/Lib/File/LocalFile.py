from __future__ import absolute_import
##########################################################################
# Ganga Project. http://cern.ch/ganga
#
# $Id: LocalFile.py,v 0.1 2011-09-29 15:40:00 idzhunov Exp $
##########################################################################

from Ganga.GPIDev.Schema import Schema, Version, SimpleItem, ComponentItem

from .IGangaFile import IGangaFile

from Ganga.GPIDev.Base.Proxy import GPIProxyObjectFactory

from Ganga.GPIDev.Lib.File import File
from Ganga.GPIDev.Lib.File import FileBuffer

import Ganga.Utility.logging
logger = Ganga.Utility.logging.getLogger()

import re
import os

regex = re.compile('[*?\[\]]')


class LocalFile(IGangaFile):

    """LocalFile represents base class for output files, such as MassStorageFile, LCGSEFile, etc 
    """
    _schema = Schema(Version(1, 1), {'namePattern': SimpleItem(defvalue="", doc='pattern of the file name'),
                                     'localDir': SimpleItem(defvalue="", doc='local dir where the file is stored, used from get and put methods'),
                                     'subfiles': ComponentItem(category='gangafiles', defvalue=[], hidden=1, typelist=['Ganga.GPIDev.Lib.File.LocalFile'], sequence=1, copyable=0, doc="collected files from the wildcard namePattern"),

                                     'compressed': SimpleItem(defvalue=False, typelist=['bool'], protected=0, doc='wheather the output file should be compressed before sending somewhere')})
    _category = 'gangafiles'
    _name = "LocalFile"
    _exportmethods = ["location", "remove", "accessURL"]

    def __init__(self, namePattern='', localDir='', **kwds):
        """ name is the name of the output file that is going to be processed
            in some way defined by the derived class
        """
        super(LocalFile, self).__init__()

        self.tmp_pwd = None

        if isinstance(namePattern, str):
            self.namePattern = namePattern
        elif isinstance(namePattern, File):
            import os.path
            self.namePattern = os.path.basename(namePattern.name)
            self.localDir = os.path.dirname(namePattern.name)
        elif isinstance(namePattern, FileBuffer):
            namePattern.create()
            import os.path
            self.namePattern = os.path.basename(namePattern.name)
            self.localDir = os.path.dirname(namePattern.name)
        else:
            logger.error(
                "Unkown type: %s . Cannot Create LocalFile from this!" % str(type(namePattern)))

        if isinstance(localDir, str):
            if localDir != '':
                self.localDir = localDir
            else:
                from os.path import abspath
                this_pwd = abspath('.')
                self.tmp_pwd = this_pwd
        else:
            logger.error(
                "Unkown type: %s . Cannot set LocalFile localDir using this!" % str(type(localDir)))

    def __construct__(self, args):

        from Ganga.GPIDev.Lib.File.SandboxFile import SandboxFile
        if len(args) == 1 and isinstance(args[0], str):
            self.namePattern = args[0]
        elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], str):
            self.namePattern = args[0]
            self.localDir = args[1]
        elif len(args) == 1 and isinstance(args[0], SandboxFile):
            super(LocalFile, self).__construct__(args)

    def __repr__(self):
        """Get the representation of the file."""

        return "LocalFile(namePattern='%s')" % self.namePattern

    def location(self):
        return self.getFilenameList()

    def accessURL(self):
        URLs = []
        for file in self.location():
            import os
            URLs.append('file://' + os.path.join(os.sep, file))
        return URLs

    def processOutputWildcardMatches(self):
        """This collects the subfiles for wildcarded output LocalFile"""
        import glob

        fileName = self.namePattern

        if self.compressed:
            fileName = '%s.gz' % self.namePattern

        sourceDir = self.getJobObject().outputdir
        if regex.search(fileName) is not None:

            for currentFile in glob.glob(os.path.join(sourceDir, fileName)):

                d = LocalFile(namePattern=os.path.basename(currentFile))
                d.compressed = self.compressed

                self.subfiles.append(GPIProxyObjectFactory(d))

    def processWildcardMatches(self):

        if self.subfiles:
            return self.subfiles

        import glob

        fileName = self.namePattern

        if self.compressed:
            fileName = '%s.gz' % self.namePattern

        sourceDir = self.localDir

        if regex.search(fileName) is not None:
            for currentFile in glob.glob(os.path.join(sourceDir, fileName)):
                d = LocalFile(namePattern=os.path.basename(
                    currentFile), localDir=os.path.dirname(currentFile))
                d.compressed = self.compressed

                self.subfiles.append(GPIProxyObjectFactory(d))

    def getFilenameList(self):
        """Return the files referenced by this LocalFile"""
        filelist = []
        self.processWildcardMatches()
        if self.subfiles:
            for f in self.subfiles:
                filelist.append(os.path.join(f.localDir, f.namePattern))
        else:
            if self.localDir == '':
                if os.path.exists(os.path.join(self.tmp_pwd, self.namePattern)):
                    self.localDir = self.tmp_pwd
                    logger.debug("File: %s found, Setting localDir: %s" % (str(self.namePattern), self.localDir))
                else:
                    from os.path import abspath
                    this_pwd = abspath('.')
                    now_tmp_pwd = this_pwd
                    if os.path.exists(os.path.join(now_tmp_pwd, self.namePattern)):
                        self.localDir = now_tmp_pwd
                        logger.debug("File: %s found, Setting localDir: %s" % (str(self.namePattern), self.localDir))
                    else:
                        logger.debug("File: %s NOT found, NOT setting localDir: %s !!!" % (str(self.namePattern), self.localDir))

            filelist.append(os.path.join(self.localDir, self.namePattern))

        return filelist

    def hasMatchedFiles(self):
        """
        OK for checking subfiles but of no wildcards, need to actually check file exists
        """

        # check for subfiles
        if len(self.subfiles) > 0:
            # we have subfiles so we must have actual files associated
            return True
        else:
            if self.containsWildcards():
                return False

        # check if single file exists (no locations field to try)
        job = self._getParent()
        if job:
            fname = self.namePattern
            if self.compressed:
                fname += ".gz"

            if os.path.isfile(os.path.join(job.getOutputWorkspace().getPath(), fname)):
                return True

        return False

    def remove(self):

        for file in self.getFilenameList():
            _actual_delete = False
            keyin = None
            while keyin == None:
                keyin = raw_input(
                    "Do you want to remove the LocalFile: %s ? [y/n] " % str(file))
                if keyin == 'y':
                    _actual_delete = True
                elif keyin == 'n':
                    _actual_delete = False
                else:
                    logger.warning("y/n please!")
                    keyin = None
            if _actual_delete:
                if not os.path.exists(file):
                    logger.warning(
                        "File %s did not exist, can't delete" % file)
                else:
                    logger.info("Deleting: %s" % file)
                    os.unlink(file)

        return
