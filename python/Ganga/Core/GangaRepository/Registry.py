import Ganga.Utility.logging

from Ganga.Core import GangaException
from Ganga.Core.GangaRepository import InaccessibleObjectError

import time
import threading

from Ganga.GPIDev.Base.Proxy import stripProxy, isType, getName

logger = Ganga.Utility.logging.getLogger()

class RegistryError(GangaException):

    def __init__(self, what=''):
        super(RegistryError, self).__init__(self, what)
        self.what = what

    def __str__(self):
        return "RegistryError: %s" % self.what


class RegistryAccessError(RegistryError):

    """ This error is raised if the request is valid in principle, 
        but the Registry cannot be accessed at the moment."""

    def __init__(self, what=''):
        super(RegistryAccessError, self).__init__(what)

    def __str__(self):
        return "RegistryAccessError: %s" % self.what


class RegistryLockError(RegistryError):

    """ This error is raised if the request is valid in principle,
        but the object is locked by another Ganga session"""

    def __init__(self, what=''):
        super(RegistryLockError, self).__init__(what)

    def __str__(self):
        return "RegistryLockError: %s" % self.what


class ObjectNotInRegistryError(RegistryError):

    """ This error is raised if an object has been associated to this registry,
        but is not actually in the registry. This most probably indicates an internal Ganga error."""

    def __init__(self, what=''):
        super(ObjectNotInRegistryError, self).__init__(what)

    def __str__(self):
        return "ObjectNotInRegistryError: %s" % self.what


class RegistryKeyError(RegistryError, KeyError):

    """ This error is raised if the given id is not found in the registry """

    def __init__(self, what=''):
        super(RegistryKeyError, self).__init__(what)

    def __str__(self):
        return "RegistryKeyError: %s" % self.what


class RegistryIndexError(RegistryError, IndexError):

    """ This error is raised if the given id is not found in the registry """

    def __init__(self, what=''):
        super(RegistryIndexError, self).__init__(what)

    def __str__(self):
        return "RegistryIndexError: %s" % self.what


def makeRepository(registry):
    """Factory that selects, imports and instantiates the correct GangaRepository"""
    if registry.type in ["LocalXML", "LocalPickle"]:
        from Ganga.Core.GangaRepository.GangaRepositoryXML import GangaRepositoryLocal
        return GangaRepositoryLocal(registry)
    elif registry.type in ["SQLite"]:
        from Ganga.Core.GangaRepository.GangaRepositorySQLite import GangaRepositorySQLite
        return GangaRepositorySQLite(registry)
    elif registry.type in ["Transient"]:
        return GangaRepository(registry)
    elif registry.type in ["ImmutableTransient"]:
        from Ganga.Core.GangaRepository.GangaRepositoryImmutableTransient import GangaRepositoryImmutableTransient
        return GangaRepositoryImmutableTransient(registry, registry.location, registry.file_ext, registry.pickle_files)
    else:
        raise RegistryError("Repository %s: Unknown repository type %s" % (registry.name, registry.type))


class IncompleteObject(object):

    """ This class represents an object that could not be loaded on startup"""

    def __init__(self, registry, id):
        self.registry = registry
        self.id = id

    def reload(self):
        self.registry._lock.acquire()
        try:
            self.registry.repository.load([self.id])
            logger.debug("Successfully reloaded '%s' object #%i!" %
                         (self.registry.name, self.id))
            for d in self.registry.changed_ids.itervalues():
                d.add(id)
        finally:
            self.registry._lock.release()

    def remove(self):
        self.registry._lock.acquire()
        try:
            if len(self.registry.repository.lock([self.id])) == 0:
                errstr = "Could not lock '%s' object #%i!" % (
                    self.registry.name, self.id)
                try:
                    errstr += " Object is locked by session '%s' " % self.registry.repository.get_lock_session(self.id)
                except Exception as err:
                    logger.debug("Remove Lock error: %s" % str(err))
                raise RegistryLockError(errstr)
            self.registry.repository.delete([self.id])
            for d in self.registry.changed_ids.itervalues():
                d.add(id)
        finally:
            self.registry._lock.release()

    def __repr__(self):
        return "Incomplete object in '%s', ID %i. Try reload() or remove()." % (self.registry.name, self.id)


class Registry(object):

    """Ganga Registry
    Base class providing a dict-like locked and lazy-loading interface to a Ganga repository
    """

    def __init__(self, name, doc, dirty_flush_counter=10, update_index_time=30):
        """Registry constructor, giving public name and documentation"""
        self.name = name
        self.doc = doc
        self._started = False
        self.dirty_flush_counter = dirty_flush_counter
        self.dirty_objs = {}
        self.dirty_hits = 0
        self.update_index_time = update_index_time
        self._update_index_timer = 0
        self._needs_metadata = False
        self.metadata = None
        self._lock = threading.RLock()
        self.changed_ids = {}

# Methods intended to be called from ''outside code''
    def __getitem__(self, id):
        """ Returns the Ganga Object with the given id.
            Raise RegistryKeyError"""
        try:
            return self._objects[id]
        except KeyError, err:
            logger.debug("Repo KeyError: %s" % str(err))
            if id in self._incomplete_objects:
                return IncompleteObject(self, id)
            raise RegistryKeyError("Could not find object #%s" % id)

    def __len__(self):
        """ Returns the current number of root objects """
        return len(self._objects)

    def __contains__(self, id):
        """ Returns True if the given ID is in the registry """
        return id in self._objects

    def updateLocksNow(self):
        self.repository.updateLocksNow()
        return

    def ids(self):
        """ Returns the list of ids of this registry """
        if self._started and time.time() > self._update_index_timer + self.update_index_time:
            self._lock.acquire()
            try:
                changed_ids = self.repository.update_index()
                for d in self.changed_ids.itervalues():
                    d.update(changed_ids)
            finally:
                self._lock.release()
            self._update_index_timer = time.time()

        return sorted(self._objects.keys())

    def items(self):
        """ Return the items (ID,obj) in this registry. 
        Recommended access for iteration, since accessing by ID can fail if the ID iterator is old"""
        if self._started and time.time() > self._update_index_timer + self.update_index_time:
            self._lock.acquire()
            try:
                changed_ids = self.repository.update_index()
                for d in self.changed_ids.itervalues():
                    d.update(changed_ids)
            finally:
                self._lock.release()
            self._update_index_timer = time.time()

        return sorted(self._objects.items())

    def iteritems(self):
        """ Return the items (ID,obj) in this registry."""
        return self.items()

    def keys(self):
        """ Returns the list of ids of this registry """
        return self.ids()

    def values(self):
        """ Return the objects in this registry, in order of ID.
        Besides items() this is also recommended for iteration."""
        return [it[1] for it in self.items()]

    def __iter__(self):
        return iter(self.values())

    def find(self, _obj):
        """Returns the id of the given object in this registry, or 
        Raise ObjectNotInRegistryError if the Object is not found"""
        obj = stripProxy(_obj)
        try:
            if hasattr(obj, '_registry_id'):
                assert obj == self._objects[obj._registry_id]
                return obj._registry_id
            else:
                raise ObjectNotInRegistryError("Object %s does not seem to be in this registry!" % getName(obj))
        except AttributeError, err:
            logger.debug("%s" % str(err))
            raise ObjectNotInRegistryError("Object %s does not seem to be in any registry!" % getName(obj))
        except AssertionError, err:
            logger.warning("%s" % str(err))
            from Ganga.GPIDev.Lib.JobTree import JobTree
            if isType(obj, JobTree):
                return obj._registry_id
            import traceback
            traceback.print_stack()
            raise ObjectNotInRegistryError("Object %s is a duplicated version of the one in this registry!" % getName(obj))
        except KeyError, err:
            logger.debug("%s", str(err))
            raise ObjectNotInRegistryError("Object %s does not seem to be in this registry!" % getName(obj))

    def clean(self, force=False):
        """Deletes all elements of the registry, if no other sessions are present.
        if force == True it removes them regardless of other sessions.
        Returns True on success, False on failure."""
        if not self._started:
            raise RegistryAccessError(
                "Cannot clean a disconnected repository!")
        self._lock.acquire()
        try:
            if not force:
                other_sessions = self.repository.get_other_sessions()
                if len(other_sessions) > 0:
                    logger.error(
                        "The following other sessions are active and have blocked the clearing of the repository: \n * %s" % ("\n * ".join(other_sessions)))
                    return False
            self.repository.reap_locks()
            self.repository.delete(self._objects.keys())
            self.dirty_objs = {}
            self.dirty_hits = 0
            self.changed_ids = {}
            self.repository.clean()
        finally:
            self._lock.release()

# Methods that can be called by derived classes or Ganga-internal classes like Job
# if the dirty objects list is modified, the methods must be locked by self._lock
# all accesses to the repository must also be locked!

    def _add(self, obj, force_index=None):
        """ Add an object to the registry and assigns an ID to it. 
        use force_index to set the index (for example for metadata). This overwrites existing objects!
        Raises RepositoryError"""
        if not self._started:
            raise RegistryAccessError(
                "Cannot add objects to a disconnected repository!")
        self._lock.acquire()
        try:
            if force_index is None:
                ids = self.repository.add([obj])
            else:
                if len(self.repository.lock([force_index])) == 0:
                    raise RegistryLockError(
                        "Could not lock '%s' id #%i for a new object!" % (self.name, force_index))
                # raises exception if len(ids) < 1
                ids = self.repository.add([obj], [force_index])
            obj._registry_locked = True
            self.repository.flush(ids)
            for d in self.changed_ids.itervalues():
                d.update(ids)
            return ids[0]
        finally:
            self._lock.release()

    def _remove(self, obj, auto_removed=0):
        """ Private method removing the obj from the registry. This method always called.
        This method may be overriden in the subclass to trigger additional actions on the removal.
        'auto_removed' is set to true if this method is called in the context of obj.remove() method to avoid recursion.
        Only then the removal takes place. In the opposite case the obj.remove() is called first which eventually calls
        this method again with "auto_removed" set to true. This is done so that obj.remove() is ALWAYS called once independent
        on the removing context.
        Raise RepositoryError
        Raise RegistryAccessError
        Raise RegistryLockError
        Raise ObjectNotInRegistryError"""
        if not self._started:
            raise RegistryAccessError(
                "Cannot remove objects from a disconnected repository!")
        if not auto_removed and "remove" in obj.__dict__:
            obj.remove()
        else:
            id = self.find(obj)
            try:
                self._write_access(obj)
            except RegistryKeyError, err:
                logger.debug("Registry KeyError: %s" % str(err))
                logger.warning("double delete: Object #%i is not present in registry '%s'!" % (id, self.name))
                return
            logger.debug(
                'deleting the object %d from the registry %s', id, self.name)
            self._lock.acquire()
            try:
                if obj in self.dirty_objs:
                    del self.dirty_objs[obj]
                self.repository.delete([id])
                del obj
                for d in self.changed_ids.itervalues():
                    d.add(id)
            finally:
                self._lock.release()

    def _dirty(self, obj):
        """ Mark an object as dirty.
        Trigger automatic flush after specified number of dirty hits
        Raise RepositoryError
        Raise RegistryAccessError
        Raise RegistryLockError"""
        logger.debug("_dirty(%s)" % id(obj))
        self._write_access(obj)
        self._lock.acquire()
        try:
            self.dirty_objs[obj] = 1
            self.dirty_hits += 1
            if self.dirty_hits % self.dirty_flush_counter == 0:
                self._flush()
            # HACK for GangaList: there _dirty is called _before_ the object is
            # modified
            self.dirty_objs[obj] = 1
            for d in self.changed_ids.itervalues():
                d.add(self.find(obj))
        finally:
            self._lock.release()

    def _flush(self, objs=None):
        """Flush a set of objects to the persistency layer immediately
        Raise RepositoryError
        Raise RegistryAccessError
        Raise RegistryLockError"""

        if objs is None:
            objs = []

        logger.debug("Reg: %s _flush(%s)" % (self.name, objs))
        if not self._started:
            raise RegistryAccessError(
                "Cannot flush to a disconnected repository!")
        for obj in objs:
            self._write_access(obj)

        from Ganga.GPIDev.Lib.GangaList.GangaList import GangaList
        if not (isinstance(objs, list) or isType(objs, GangaList)):
            objs = [objs]

        self._lock.acquire()
        try:
            for obj in objs:
                self.dirty_objs[obj] = 1
            ids = []
            for obj in self.dirty_objs.keys():
                try:
                    ids.append(self.find(obj))
                except ObjectNotInRegistryError as err:
                    logger.error(" Object not in Repository: %s" % str(err))
            logger.debug("repository.flush(%s)" % ids)
            self.repository.flush(ids)
            self.dirty_objs = {}
        finally:
            self._lock.release()

    def _read_access(self, obj, sub_obj=None):
        """Obtain read access on a given object.
        sub-obj is the object the read access is actually desired (ignored at the moment)
        Raise RegistryAccessError
        Raise RegistryKeyError"""
        #logger.debug("Reg %s _read_access(%s)" % (self.name, str(obj)))
        if not obj._data or "_registry_refresh" in obj.__dict__:
            if not self._started:
                raise RegistryAccessError(
                    "The object #%i in registry '%s' is not fully loaded and the registry is disconnected! Type 'reactivate()' if you want to reconnect." % (self.find(obj), self.name))
            obj.__dict__.pop("_registry_refresh", None)
            assert not "_registry_refresh" in obj.__dict__
            self._lock.acquire()
            try:
                id = self.find(obj)
                try:
                    self.repository.load([id])
                except KeyError, err:
                    logger.debug("_read_access KeyError %s" % str(err))
                    raise RegistryKeyError("The object #%i in registry '%s' was deleted!" % (id, self.name))
                except InaccessibleObjectError as err:
                    raise RegistryKeyError("The object #%i in registry '%s' could not be accessed - %s!" % (id, self.name, str(err)))
                for d in self.changed_ids.itervalues():
                    d.add(id)
            finally:
                self._lock.release()

    def _write_access(self, _obj):
        """Obtain write access on a given object.
        Raise RepositoryError
        Raise RegistryAccessError
        Raise RegistryLockError
        Raise ObjectNotInRegistryError (via self.find())"""

        obj = stripProxy(_obj)

        #logger.debug("Reg: %s _write_access(%s)" % (self.name, str(obj)))

        # if self.name == "prep.metadata":
        #    import traceback
        #    traceback.print_stack()

        if not self._started:
            raise RegistryAccessError("Cannot get write access to a disconnected repository!")
        if not hasattr(obj, '_registry_locked') or not obj._registry_locked:
            with self._lock:
                id = self.find(obj)
                try:
                    if len(self.repository.lock([id])) == 0:
                        errstr = "Could not lock '%s' object #%i!" % (self.name, id)
                        try:
                            errstr += " Object is locked by session '%s' " % self.repository.get_lock_session(id)
                        except Exception as err:
                            logger.debug( "Locking Exception: %s" % str(err) )
                        raise RegistryLockError(errstr)
                finally:  # try to load even if lock fails
                    try:
                        obj.__dict__.pop("_registry_refresh", None)
                        self.repository.load([id])
                    except KeyError, err:
                        logger.debug("_write_access KeyError %s" % str(err))
                        raise RegistryKeyError("The object #%i in registry '%s' was deleted!" % (id, self.name))
                    except InaccessibleObjectError as err:
                        raise RegistryKeyError("The object #%i in registry '%s' could not be accessed - %s!" % (id, self.name, str(err)))
                    for d in self.changed_ids.itervalues():
                        d.add(id)
                obj._registry_locked = True
                
        return True

    def _release_lock(self, obj):
        """Release the lock on a given object.
        Raise RepositoryError
        Raise RegistryAccessError
        Raise ObjectNotInRegistryError"""
        if not self._started:
            raise RegistryAccessError(
                "Cannot manipulate locks of a disconnected repository!")
        logger.debug("Reg: %s _release_lock(%s)" % (self.name, str(id(obj))))
        self._lock.acquire()
        try:
            if obj._registry_locked:
                oid = self.find(obj)
                if obj in self.dirty_objs:
                    self.repository.flush([oid])
                    del self.dirty_objs[obj]
                obj._registry_locked = False
                self.repository.unlock([oid])
        finally:
            self._lock.release()

    def pollChangedJobs(self, name):
        """Returns a list of job ids that changed since the last call of this function.
        On first invocation returns a list of all ids.
        "name" should be a unique identifier of the user of this information."""

        self._lock.acquire()
        try:
            if self._started and time.time() > self._update_index_timer + self.update_index_time:
                changed_ids = self.repository.update_index()
                for d in self.changed_ids.itervalues():
                    d.update(changed_ids)
                self._update_index_timer = time.time()
            res = self.changed_ids.get(name, set(self.ids()))
            self.changed_ids[name] = set()
            return res
        finally:
            self._lock.release()

    def getIndexCache(self, obj):
        """Returns a dictionary to be put into obj._index_cache
        This can and should be overwritten by derived Registries to provide more index values."""
        return {}

    def startup(self):
        """Connect the repository to the registry. Called from Repository_runtime.py"""
        self._lock.acquire()
        try:
            t0 = time.time()
            self.repository = makeRepository(self)
            self._objects = self.repository.objects
            self._incomplete_objects = self.repository.incomplete_objects

            if self._needs_metadata:
                t2 = time.time()
                if self.metadata is None:
                    self.metadata = Registry(self.name + ".metadata", "Metadata repository for %s" % self.name,
                            dirty_flush_counter=self.dirty_flush_counter, update_index_time=self.update_index_time)
                    self.metadata.type = self.type
                    self.metadata.location = self.location
                    self.metadata._parent = self
                logger.debug("metadata startup")
                self.metadata.startup()
                t3 = time.time()
                logger.debug("Startup of %s.metadata took %s sec" % (str(self.name), str(t3-t2)))

            logger.debug("repo startup")
            self.repository.startup()
            # All Ids could have changed
            self.changed_ids = {}
            t1 = time.time()
            logger.debug("Registry '%s' [%s] startup time: %s sec" % (self.name, self.type, t1 - t0))
            self._started = True
        finally:
            self._lock.release()

    def shutdown(self):
        """Flush and disconnect the repository. Called from Repository_runtime.py """
        from Ganga.Utility.logging import getLogger
        logger = getLogger()
        logger.debug("Shutting Down Registry")
        self._lock.acquire()
        try:
            try:
                if not self.metadata is None:
                    try:
                        self._flush()
                    except Exception, err:
                        logger.debug("shutdown _flush Exception: %s" % str(err))
                    self.metadata.shutdown()
            except Exception as err:
                logger.debug("Exception on shutting down metadata repository '%s' registry: %s", self.name, str(err))
            try:
                self._flush()
            except Exception as err:
                logger.debug("Exception on flushing '%s' registry: %s", self.name, str(err))
            self._started = False
            for obj in self._objects.values():
                # locks are not guaranteed to survive repository shutdown
                obj._registry_locked = False
            self.repository.shutdown()
        finally:
            self._lock.release()

    def info(self, full=False):
        """Returns an informative string onFlush and disconnect the repository. Called from Repository_runtime.py """
        self._lock.acquire()
        try:
            s = "registry '%s': %i objects" % (self.name, len(self._objects))
            if full:
                other_sessions = self.repository.get_other_sessions()
                if len(other_sessions) > 0:
                    s += ", %i other concurrent sessions:\n * %s" % (len(other_sessions), "\n * ".join(other_sessions))
            return s
        finally:
            self._lock.release()

    def print_other_sessions(self):
        other_sessions = self.repository.get_other_sessions()
        if len(other_sessions) > 0:
            logger.warning("%i other concurrent sessions:\n * %s" % (len(other_sessions), "\n * ".join(other_sessions)))

