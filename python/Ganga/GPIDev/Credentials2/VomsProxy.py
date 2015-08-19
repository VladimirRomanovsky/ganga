from Ganga.GPIDev.Schema import SimpleItem
from Ganga.Utility.Shell import Shell

import Ganga.Utility.logging
logger = Ganga.Utility.logging.getLogger()

from .ICredentialInfo import ICredentialInfo, cache
from .ICredentialRequirement import ICredentialRequirement
from .exceptions import CredentialRenewalError
from Ganga.Utility.Config import getConfig

import os

import subprocess
from datetime import datetime, timedelta
from getpass import getpass


class VomsProxyInfo(ICredentialInfo):
    """
    A wrapper around a voms proxy file
    """
    
    def __init__(self, requirements, check_file=False, create=False):
        self.shell = Shell()

        super(VomsProxyInfo, self).__init__(requirements, check_file, create)

    def create(self):
        """
        Creates the grid proxy.
        
        Raises:
            CredentialRenewalError: If the renewal process returns a non-zero value
        """
        voms_command = ""
        logger.debug("require " + self.initialRequirements.vo)
        if self.initialRequirements.vo:
            voms_command = "-voms %s" % self.initialRequirements.vo
            if self.initialRequirements.group or self.initialRequirements.role:
                voms_command += ":"
                if self.initialRequirements.group:
                    voms_command += "/%s" % self.initialRequirements.group
                if self.initialRequirements.role:
                    voms_command += "/%s" % self.initialRequirements.role
        logger.debug(voms_command)
        command = 'voms-proxy-init -pwstdin -out %s %s' % (self.location, voms_command)
        logger.debug(command)
        process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdoutdata, stderrdata = process.communicate(getpass('Grid password: '))
        if process.returncode == 0:
            logger.debug('Grid proxy {path} created. Valid for {time}'.format(path=self.location, time=self.time_left()))
        else:
            raise CredentialRenewalError(stderrdata)
    
    def destroy(self):
        self.shell.cmd1("voms-proxy-destroy -file %s" % self.location, allowed_exit=[0, 1])
        
        if self.location:
            os.remove(self.location)
    
    @cache
    def info(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -all -file %s' % self.location)
        return output
    
    @property
    @cache
    def identity(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file %s -identity' % self.location)
        return output.strip()
    
    @property
    @cache
    def vo(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file %s -vo' % self.location)
        if status != 0:
            return None
        return output.split(":")[0].strip()
       
    @property
    @cache
    def role(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file %s -vo' % self.location)
        if status != 0:
            return None  # No VO
        vo_list = output.split(":")
        if len(vo_list) <= 1:
            return None  # No command after VO
        return vo_list[1].split("/")[-1].split("=")[-1].strip()
    
    @property
    @cache
    def group(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file %s -vo' % self.location)
        if status != 0:
            return None  # No VO
        vo_list = output.split(":")
        if len(vo_list) <= 1:
            return None  # No command after VO
        # TODO Make this support multiple groups and subgroups
        group_role_list = vo_list[1].split("/")
        if len(group_role_list) <= 2:
            return None  # No group specified in command
        return group_role_list[-1].strip()

    @cache
    def expiry_time(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file %s -timeleft' % self.location)
        if status != 0:
            return datetime.now()
        return datetime.now() + timedelta(seconds=int(output))


class VomsProxy(ICredentialRequirement):
    """
    An object specifying the requirements of a VOMS proxy file
    """
    _schema = ICredentialRequirement._schema.inherit_copy()
    _schema.datadict["identity"] = SimpleItem(defvalue=None, typelist=['str', 'None'], doc="Identity for the proxy")
    _schema.datadict["vo"] = SimpleItem(defvalue=None, typelist=['str', 'None'], doc="Virtual Organisation for the proxy. Defaults to LGC/VirtualOrganisation")
    _schema.datadict["role"] = SimpleItem(defvalue=None, typelist=['str', 'None'], doc="Role that the proxy must have")
    _schema.datadict["group"] = SimpleItem(defvalue=None, typelist=['str', 'None'], doc="Group for the proxy - either 'group' or 'group/subgroup'")
                                                                                
    _category = "CredentialRequirement"
    _name = "VomsProxy"
    
    _infoClass = VomsProxyInfo

    def __init__(self):
        super(VomsProxy, self).__init__()
        if not self.vo:
            self.vo = getConfig('LCG')['VirtualOrganisation']
    
    def encoded(self):
        return ':'.join(requirement for requirement in [self.identity, self.vo, self.role, self.group] if requirement)  # filter out the empties
    
    def is_empty(self):
        return not (self.identity or self.vo or self.role or self.group)

    def default_location(self):
        return os.getenv("X509_USER_PROXY") or "/tmp/x509up_u"+str(os.getuid())