# Note: Following stuff must be considered in a GangaRepository:
#
# * lazy loading
# * locking

from Ganga.Core.GangaRepository import GangaRepository, RepositoryError, InaccessibleObjectError
from Ganga.Utility.Plugin import PluginManagerError
import os
import os.path
import time
import errno

from Ganga.Core.GangaRepository.SessionLock import SessionLockManager

import Ganga.Utility.logging

from Ganga.Core.GangaRepository.PickleStreamer import to_file as pickle_to_file
from Ganga.Core.GangaRepository.PickleStreamer import from_file as pickle_from_file

from Ganga.Core.GangaRepository.VStreamer import to_file as xml_to_file
from Ganga.Core.GangaRepository.VStreamer import from_file as xml_from_file
from Ganga.Core.GangaRepository.VStreamer import XMLFileError

from Ganga.GPIDev.Lib.GangaList.GangaList import GangaList, makeGangaListByRef
from Ganga.GPIDev.Base.Objects import Node
from Ganga.Core.GangaRepository import SubJobXMLList

from Ganga.GPIDev.Base.Proxy import isType, stripProxy, getName

logger = Ganga.Utility.logging.getLogger()

printed_explanation = False


def safe_save(fn, _obj, to_file, ignore_subs=''):
    """Writes a file safely, raises IOError on error"""
    obj = stripProxy(_obj)
    if hasattr(obj, 'application') and hasattr(obj.application, 'hash') and obj.application.hash is not None:
        if not obj.application.calc_hash(verify=True):
            try:
                logger.warning("%s" % str(obj.application))
                logger.warning('Protected attribute(s) of %s application (associated with %s #%s) changed!' % (getName(obj.application), getName(obj), obj._registry_id))
            except AttributeError as err:
                logger.warning('Protected attribute(s) of %s application (associated with %s) changed!!!!' % (getName(obj.application), getName(obj)))
                logger.warning("%s" % str(err))
            logger.warning('If you knowingly circumvented the protection, ignore this message (and, optionally,')
            logger.warning('re-prepare() the application). Otherwise, please file a bug report at:')
            logger.warning('https://its.cern.ch/jira/browse/GANGA')
    elif hasattr(obj, 'analysis') and hasattr(obj.analysis, 'application') and \
            hasattr(obj.analysis.application, 'hash') and obj.analysis.application.hash is not None:
        if not obj.analysis.application.calc_hash(verify=True):
            try:
                logger.warning("%s" % str(obj.analysis))
                logger.warning('Protected attribute(s) of %s application (associated with %s #%s) changed!' % (getName(obj.analysis.application), getName(obj), obj._registry_id))
            except AttributeError as err:
                logger.warning('Protected attribute(s) of %s application (associated with %s) changed!!!!' % (getName(obj.analysis.application), getName(obj)))
                logger.warning("%s" % str(err))
            logger.warning('If you knowingly circumvented the protection, ignore this message (and, optionally,')
            logger.warning('re-prepare() the application). Otherwise, please file a bug report at:')
            logger.warning('https://its.cern.ch/jira/browse/GANGA')

    if not os.path.exists(fn):
        # file does not exist, so make it fast!
        try:
            with open(fn, "w") as this_file:
                to_file(obj, this_file, ignore_subs)
            return
        except IOError as e:
            raise IOError("Could not write file '%s' (%s)" % (fn, e))
        except XMLFileError as err:
            raise err
    try:
        with open(fn + ".new", "w") as tmpfile:
            to_file(obj, tmpfile, ignore_subs)
            # Important: Flush, then sync file before renaming!
            # tmpfile.flush()
            # os.fsync(tmpfile.fileno())
    except IOError as e:
        raise IOError("Could not write file %s.new (%s)" % (fn, e))
    except XMLFileError as err:
        raise err
    # Try to make backup copy...
    try:
        rmrf(fn + "~")
    except OSError as e:
        logger.debug("Error on removing old backup file %s~ (%s) " % (fn, e))
    try:
        os.rename(fn, fn + "~")
    except OSError as e:
        logger.debug("Error on file backup %s (%s) " % (fn, e))
    try:
        os.rename(fn + ".new", fn)
    except OSError as e:
        raise IOError("Error on moving file %s.new (%s) " % (fn, e))


def rmrf(name, count=0):

    if count != 0:
        logger.debug("Trying again to remove: %s" % str(name))
        if count == 3:
            logger.error("Tried 3 times to remove file/folder: %s" % str(name))
            from Ganga.Core.exceptions import GangaException
            raise GangaException("Failed to remove file/folder: %s" % str(name))

    if os.path.isdir(name):

        try:
            remove_name = name + "_" + str(time.time()) + '__to_be_deleted_'
            os.rename(name, remove_name)
            logger.debug("Move completed")
        except OSError as err:
            if err.errno != errno.ENOENT:
                logger.debug("rmrf Err: %s" % str(err))
                remove_name = name
                raise err
            return

        for sfn in os.listdir(remove_name):
            try:
                rmrf(os.path.join(remove_name, sfn), count)
            except OSError as err:
                if err.errno == errno.EBUSY:
                    logger.debug("rmrf Remove err: %s" % str(err))
                    ## Sleep 2 sec and try again
                    time.sleep(2.)
                    rmrf(os.path.join(remove_name, sfn), count+1)
        try:
            os.removedirs(remove_name)
        except OSError as err:
            if err.errno == errno.ENOTEMPTY:
                rmrf(remove_name, count+1)
            elif err.errno != errno.ENOENT:
                logger.debug("%s" % str(err))
                raise err
            return
    else:
        try:
            remove_name = name + "_" + str(time.time()) + '__to_be_deleted_'
            os.rename(name, remove_name)
        except OSError as err:
            if err.errno not in [errno.ENOENT, errno.EBUSY]:
                raise err
            logger.debug("rmrf Move err: %s" % str(err))
            if err.errno == errno.EBUSY:
                rmrf(name, count+1)
            return

        try:
            os.remove(remove_name)
        except OSError as err:
            if err.errno != errno.ENOENT:
                logger.debug("%s" % str(err))
                raise err
            return


class GangaRepositoryLocal(GangaRepository):

    """GangaRepository Local"""

    def __init__(self, registry):
        super(GangaRepositoryLocal, self).__init__(registry)
        self.dataFileName = "data"
        self.sub_split = "subjobs"
        self.root = os.path.join(self.registry.location, "6.0", self.registry.name)
        self.lockroot = os.path.join(self.registry.location, "6.0")
        self.saved_paths = {}
        self.saved_idxpaths = {}

    def startup(self):
        """ Starts a repository and reads in a directory structure.
        Raise RepositoryError"""
        self._load_timestamp = {}

        # New Master index to speed up loading of many, MANY files
        self._cache_load_timestamp = {}
        self._cached_cat = {}
        self._cached_cls = {}
        self._cached_obj = {}
        self._master_index_timestamp = 0

        self.known_bad_ids = []
        if "XML" in self.registry.type:
            self.to_file = xml_to_file
            self.from_file = xml_from_file
        elif "Pickle" in self.registry.type:
            self.to_file = pickle_to_file
            self.from_file = pickle_from_file
        else:
            raise RepositoryError(self.repo, "Unknown Repository type: %s" % self.registry.type)
        self.sessionlock = SessionLockManager(self, self.lockroot, self.registry.name)
        self.sessionlock.startup()
        # Load the list of files, this time be verbose and print out a summary
        # of errors
        self.update_index(verbose=True, firstRun=True)
        logger.debug("GangaRepositoryLocal Finished Startup")

    def shutdown(self):
        """Shutdown the repository. Flushing is done by the Registry
        Raise RepositoryError"""
        from Ganga.Utility.logging import getLogger
        logger = getLogger()
        logger.debug("Shutting Down GangaRepositoryLocal: %s" % self.registry.name)
        self._write_master_cache()
        self.sessionlock.shutdown()

    def get_fn(self, id):
        """ Returns the file name where the data for this object id is saved"""
        if id not in self.saved_paths:
            self.saved_paths[id] = os.path.join(self.root, "%ixxx" % int(id * 0.001), "%i" % id, self.dataFileName)
        return self.saved_paths[id]

    def get_idxfn(self, id):
        """ Returns the file name where the data for this object id is saved"""
        if id not in self.saved_idxpaths:
            self.saved_idxpaths[id] = os.path.join(self.root, "%ixxx" % int(id * 0.001), "%i.index" % id)
        return self.saved_idxpaths[id]

    def index_load(self, id):
        """ load the index file for this object if necessary
            Loads if never loaded or timestamp changed. Creates object if necessary
            Returns True if this object has been changed, False if not
            Raise IOError on access or unpickling error 
            Raise OSError on stat error
            Raise PluginManagerError if the class name is not found"""
        #logger.debug("Loading index %s" % id)
        fn = self.get_idxfn(id)
        # index timestamp changed
        if self._cache_load_timestamp.get(id, 0) != os.stat(fn).st_ctime:
            try:
                with open(fn, 'r') as fobj:
                    cat, cls, cache = pickle_from_file(fobj)[0]
            except Exception as x:
                logger.debug("index_load Exception: %s" % str(x))
                raise IOError("Error on unpickling: %s %s" %(getName(x), x))
            if id in self.objects:
                obj = self.objects[id]
                if obj._data:
                    obj.__dict__["_registry_refresh"] = True
            else:
                obj = self._make_empty_object_(id, cat, cls)
            obj._index_cache = cache
            self._cache_load_timestamp[id] = os.stat(fn).st_ctime
            self._cached_cat[id] = cat
            self._cached_cls[id] = cls
            self._cached_obj[id] = cache
            return True
        elif id not in self.objects:
            self.objects[id] = self._make_empty_object_(
                id, self._cached_cat[id], self._cached_cls[id])
            self.objects[id]._index_cache = self._cached_obj[id]
            return True
        return False

    def index_write(self, id):
        """ write an index file for this object (must be locked).
            Should not raise any Errors """
        obj = self.objects[id]
        try:
            ifn = self.get_idxfn(id)
            new_idx_cache = self.registry.getIndexCache(obj)
            if new_idx_cache != obj._index_cache or not os.path.exists(ifn):
                obj._index_cache = new_idx_cache
                with open(ifn, "w") as this_file:
                    pickle_to_file((obj._category, getName(obj), obj._index_cache), this_file)
        except IOError as err:
            logger.error("Index saving to '%s' failed: %s %s" % (ifn, getName(err), str(err)))

    def get_index_listing(self):
        """Get dictionary of possible objects in the Repository: True means index is present,
            False if not present
        Raise RepositoryError"""
        try:
            obj_chunks = [d for d in os.listdir(self.root) if d.endswith("xxx") and d[:-3].isdigit()]
        except OSError as err:
            logger.debug("get_index_listing Exception: %s" % str(err))
            raise RepositoryError(self, "Could not list repository '%s'!" % (self.root))
        objs = {}  # True means index is present, False means index not present
        for c in obj_chunks:
            try:
                listing = os.listdir(os.path.join(self.root, c))
            except OSError as err:
                logger.debug("get_index_listing Exception: %s")
                raise RepositoryError(self, "Could not list repository '%s'!" % (os.path.join(self.root, c)))
            objs.update(dict([(int(l), False)
                              for l in listing if l.isdigit()]))
            for l in listing:
                if l.endswith(".index") and l[:-6].isdigit():
                    id = int(l[:-6])
                    if id in objs:
                        objs[id] = True
                    else:
                        try:
                            rmrf(self.get_idxfn(id))
                            logger.warning("Deleted index file without data file: %s" % self.get_idxfn(id))
                        except OSError as err:
                            logger.debug("get_index_listing delete Exception: %s" % str(err))
        return objs

    def _read_master_cache(self):
        try:
            _master_idx = os.path.join(self.root, 'master.idx')
            if os.path.isfile(_master_idx):
                logger.debug("Reading Master index")
                self._master_index_timestamp = os.stat(_master_idx).st_ctime
                with open(_master_idx, 'r') as input_f:
                    this_master_cache = pickle_from_file(input_f)[0]
                for this_cache in this_master_cache:
                    this_id = this_cache[0]
                    self._cache_load_timestamp[this_id] = this_cache[1]
                    self._cached_cat[this_id] = this_cache[2]
                    self._cached_cls[this_id] = this_cache[3]
                    self._cached_obj[this_id] = this_cache[4]
            else:
                logger.debug("Not Reading Master Index")
        except Exception as err:
            Ganga.Utility.logging.log_unknown_exception()
            logger.debug("Master Index corrupt, ignoring it")
            logger.debug("Exception: %s" % str(err))
            for k, v in self._cache_load_timestamp.iteritems():
                self._cache_load_timestamp.pop(k)
            for k, v in self._cached_cat.iteritems():
                self._cached_cat.pop(k)
            for k, v in self._cached_cls.iteritems():
                self._cached_cls.pop(k)
            for k, v in self._cached_obj.iteritems():
                self._cached_obj.pop(k)
        return

    def _write_master_cache(self, shutdown=False):
        logger.debug("Updating master index")
        try:
            _master_idx = os.path.join(self.root, 'master.idx')
            this_master_cache = []
            if os.path.isfile(_master_idx) and not shutdown:
                if abs(self._master_index_timestamp - os.stat(_master_idx).st_ctime) < 300:
                    return
            items_to_save = self.objects.iteritems()
            for k, v in items_to_save:
                try:
                    # Check and write index first
                    obj = self.objects[k]
                    new_index = None
                    if obj is not None:
                        new_index = self.registry.getIndexCache(obj)
                    if new_index is not None and new_index != obj._index_cache:
                        arr_k = [k]
                        if len(self.lock(arr_k)) != 0:
                            self.index_write(arr_k)
                            self.unlock(arr_k)
                except Exception as err:
                    logger.debug("Failed to update index: %s on startup/shutdown" % str(k))
                    logger.debug("Reason: %s" % str(err))
            cached_list = []
            iterables = self._cache_load_timestamp.iteritems()
            for k, v in iterables:
                cached_list.append(k)
                try:
                    fn = self.get_idxfn(k)
                    time = os.stat(fn).st_ctime
                except OSError as err:
                    logger.debug("_write_master_cache: %s" % str(err))
                    import errno
                    if err.errno == errno.ENOENT:  # If file is not found
                        time = 0
                    else:
                        raise
                cached_list.append(time)
                cached_list.append(self._cached_cat[k])
                cached_list.append(self._cached_cls[k])
                cached_list.append(self._cached_obj[k])
                this_master_cache.append(cached_list)

            try:
                with open(_master_idx, 'w') as of:
                    pickle_to_file(this_master_cache, of)
            except IOError as err:
                logger.debug("write_master: %s" % str(err))
                try:
                    os.remove(os.path.join(self.root, 'master.idx'))
                except OSError as x:
                    Ganga.Utility.logging.log_user_exception(debug=True)
        except Exception as err:
            logger.debug("write_error2: %s" % str(err))
            Ganga.Utility.logging.log_unknown_exception()

        return

    def updateLocksNow(self):
        self.sessionlock.updateNow()

    def update_index(self, id=None, verbose=False, firstRun=False):
        """ Update the list of available objects
        Raise RepositoryError"""
        # First locate and load the index files
        logger.debug("updating index...")
        objs = self.get_index_listing()
        changed_ids = []
        deleted_ids = set(self.objects.keys())
        summary = []
        if firstRun:
            self._read_master_cache()
        for id, idx in objs.iteritems():
            deleted_ids.discard(id)
            # Make sure we do not overwrite older jobs if someone deleted the
            # count file
            if id > self.sessionlock.count:
                self.sessionlock.count = id + 1
            # Locked IDs can be ignored
            if id in self.sessionlock.locked:
                continue
            # Now we treat unlocked IDs
            try:
                # if this succeeds, all is well and we are done
                if self.index_load(id):
                    changed_ids.append(id)
                continue
            except IOError as err:
                logger.debug("IOError: Failed to load index %i: %s" % (id, str(err)))
            except OSError as err:
                logger.debug("OSError: Failed to load index %i: %s" % (id, str(err)))
            except PluginManagerError as err:
                # Probably should be DEBUG
                logger.debug("PluginManagerError: Failed to load index %i: %s" % (id, str(err)))
                # This is a FATAL error - do not try to load the main file, it
                # will fail as well
                summary.append((id, err))
                continue

            # print id
            # print self.objects

            # this is bad - no or corrupted index but object not loaded yet!
            # Try to load it!
            if not id in self.objects:
                try:
                    self.load([id])
                    changed_ids.append(id)
                    # Write out a new index if the file can be locked
                    if len(self.lock([id])) != 0:
                        self.index_write(id)
                        self.unlock([id])
                except KeyError as err:
                    logger.debug("update Error: %s" % str(err))
                    # deleted job
                    if id in self.objects:
                        self._internal_del__(id)
                        changed_ids.append(id)
                except Exception as x:
                    ## WE DO NOT CARE what type of error occured here and it can be
                    ## due to corruption so could be one of MANY exception types
                    ## If the job is not accessible this should NOT cause the loading of ganga to fail!
                    ## we can't reasonably write all possible exceptions here!
                    logger.debug("Failed to load id %i: %s" % (id, str(x)))
                    summary.append((id, str(x)))

        # Check deleted files:
        for id in deleted_ids:
            self._internal_del__(id)
            changed_ids.append(id)
        if len(deleted_ids) > 0:
            logger.warning("Registry '%s': Job %s externally deleted." % (self.registry.name, ",".join(map(str, list(deleted_ids)))))

        if len(summary) > 0:
            cnt = {}
            examples = {}
            for id, x in summary:
                if id in self.known_bad_ids:
                    continue
                cnt[getName(x)] = cnt.get(getName(x), []) + [str(id)]
                examples[getName(x)] = str(x)
                self.known_bad_ids.append(id)
                # add object to incomplete_objects
                if not id in self.incomplete_objects:
                    self.incomplete_objects.append(id)
            global printed_explanation
            for exc, ids in cnt.items():
                if examples[exc].find('comments') > 0:
                    printed_explanation = True
                    from Ganga.Utility.repairJobRepository import repairJobRepository
                    for jobid in ids:
                        repairJobRepository(int(jobid))
                else:
                    logger.error("Registry '%s': Failed to load %i jobs (IDs: %s) due to '%s' (first error: %s)" % (
                        self.registry.name, len(ids), ",".join(ids), exc, examples[exc]))
            if not printed_explanation:
                logger.error("If you want to delete the incomplete objects, you can type 'for i in %s.incomplete_ids(): %s(i).remove()' (press 'Enter' twice)" % (
                    self.registry.name, self.registry.name))
                logger.error(
                    "WARNING!!! This will result in corrupt jobs being completely deleted!!!")
                printed_explanation = True
        logger.debug("updated index done")

        if len(changed_ids) != 0:
            self._write_master_cache(shutdown=True)

        return changed_ids

    def add(self, objs, force_ids=None):
        """ Add the given objects to the repository, forcing the IDs if told to.
        Raise RepositoryError"""
        if not force_ids is None:  # assume the ids are already locked by Registry
            if not len(objs) == len(force_ids):
                raise RepositoryError(
                    self, "Internal Error: add with different number of objects and force_ids!")
            ids = force_ids
        else:
            ids = self.sessionlock.make_new_ids(len(objs))
        for i in range(0, len(objs)):
            fn = self.get_fn(ids[i])
            try:
                os.makedirs(os.path.dirname(fn))
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise RepositoryError( self, "OSError on mkdir: %s" % (str(e)))
            self._internal_setitem__(ids[i], objs[i])
            # Set subjobs dirty - they will not be flushed if they are not.
            if self.sub_split and self.sub_split in objs[i]._data:
                try:
                    for j in range(len(objs[i]._data[self.sub_split])):
                        objs[i]._data[self.sub_split][j]._dirty = True
                except AttributeError as err:
                    logger.debug("RepoXML add Exception: %s" % str(err))
        return ids

    def _safe_flush_xml(self, id):

        fn = self.get_fn(id)
        obj = self.objects[id]
        from Ganga.Core.GangaRepository.VStreamer import EmptyGangaObject
        if not isType(obj, EmptyGangaObject):
            split_cache = None

            has_children = (not self.sub_split is None) and (self.sub_split in obj._data) and len(obj._data[self.sub_split]) > 0

            if has_children:
            
                if hasattr(obj._data[self.sub_split], 'flush'):
                    # I've been read from disk in the new SubJobXMLList format I know how to flush
                    obj._data[self.sub_split].flush()
                else:
                    # I have been constructed in this session, I don't know how to flush!
                    if hasattr(obj._data[self.sub_split][0], "_dirty"):
                        split_cache = obj._data[self.sub_split]
                        for i in range(len(split_cache)):
                            if not split_cache[i]._dirty:
                                continue
                            sfn = os.path.join(os.path.dirname(fn), str(i), self.dataFileName)
                            try:
                                os.makedirs(os.path.dirname(sfn))
                            except OSError as e:
                                if e.errno != errno.EEXIST:
                                    raise RepositoryError(self, "OSError: " + str(e))
                            safe_save(sfn, split_cache[i], self.to_file)
                            split_cache[i]._setFlushed()
                    from Ganga.Core.GangaRepository import SubJobXMLList
                    # Now generate an index file to take advantage of future non-loading goodness
                    tempSubJList = SubJobXMLList.SubJobXMLList(os.path.dirname(fn), self.registry, self.dataFileName, False)
                    tempSubJList._setParent(obj)
                    tempSubJList.write_subJobIndex()
                    del tempSubJList

                safe_save(fn, obj, self.to_file, self.sub_split)
                # clean files not in subjobs anymore... (bug 64041)
                for idn in os.listdir(os.path.dirname(fn)):
                    split_cache = obj._data[self.sub_split]
                    if idn.isdigit() and int(idn) >= len(split_cache):
                        rmrf(os.path.join(os.path.dirname(fn), idn))
            else:
                safe_save(fn, obj, self.to_file, "")
                # clean files leftover from sub_split
                for idn in os.listdir(os.path.dirname(fn)):
                    if idn.isdigit():
                        rmrf(os.path.join(os.path.dirname(fn), idn))
            self.index_write(id)
            obj._setFlushed()
        else:
            raise RepositoryError(self, "Cannot flush an Empty object for ID: %s" % str(id))

    def flush(self, ids):
        logger.debug("Flushing: %s" % ids)
        #import traceback
        # traceback.print_stack()
        for id in ids:
            try:

                self._safe_flush_xml(id)

            except (OSError, IOError, XMLFileError) as x:
                raise RepositoryError(self, "Error of type: %s on flushing id '%s': %s" % (type(x), str(id), str(x)))

    def is_loaded(self, id):

        return (id in self.objects) and (self.objects[id]._data is not None)

    def count_nodes(self, id):

        node_count = 0
        fn = self.get_fn(id)

        ld = os.listdir(os.path.dirname(fn))
        i = 0
        while str(i) in ld:
            sfn = os.path.join(os.path.dirname(fn), str(i), self.dataFileName)
            if os.path.exists(sfn):
                node_count = node_count + 1
            i += 1

        return node_count

    def _actually_load_xml(self, fobj, fn, id, load_backup):

        must_load = (not id in self.objects) or (self.objects[id]._data is None)
        tmpobj = None
        if must_load or (self._load_timestamp.get(id, 0) != os.fstat(fobj.fileno()).st_ctime):
            tmpobj, errs = self.from_file(fobj)

            has_children = (self.sub_split is not None) and (self.sub_split in tmpobj._data) and len(tmpobj._data[self.sub_split]) == 0

            if has_children:
                logger.debug("Initializing SubJobXMLList")
                tmpobj._data[self.sub_split] = SubJobXMLList.SubJobXMLList(os.path.dirname(fn), self.registry, self.dataFileName, load_backup)
                logger.debug("Constructed SubJobXMLList")

            if id in self.objects:
                obj = self.objects[id]
                obj._data = tmpobj._data
                # Fix parent for objects in _data (necessary!)
                for node_key, node_obj in obj._data.items():
                    if isType(node_obj, Node):
                        node_obj._setParent(obj)
                    if (isType(node_obj, list) or isType(node_obj, GangaList)):
                        # set the parent of the list or dictionary (or other iterable) items
                        for elem in node_obj:
                            if isType(elem, Node):
                                elem._setParent(obj)

                # Check if index cache; if loaded; was valid:
                if obj._index_cache is not None:
                    new_idx_cache = self.registry.getIndexCache(obj)
                    if new_idx_cache != obj._index_cache:
                        # index is wrong! Try to get read access - then we can fix this
                        if len(self.lock([id])) != 0:
                            self.index_write(id)
                            # self.unlock([id])

                            old_idx_subset = all((k in new_idx_cache and new_idx_cache[k] == v) for k, v in obj._index_cache.iteritems())
                            if not old_idx_subset:
                                # Old index cache isn't subset of new index cache
                                new_idx_subset = all((k in obj._index_cache and obj._index_cache[k] == v) for k, v in new_idx_cache.iteritems())
                            else:
                                # Old index cache is subset of new index cache so no need to check
                                new_idx_subset = True

                            if not old_idx_subset and not new_idx_subset:
                                logger.warning("Incorrect index cache of '%s' object #%s was corrected!" % (self.registry.name, id))
                                logger.debug("old cache: %s\t\tnew cache: %s" % (str(obj._index_cache), str(new_idx_cache)))
                                self.unlock([id])
                        else:
                            pass
                            # if we cannot lock this, the inconsistency is
                            # most likely the result of another ganga
                            # process modifying the repo
                        obj._index_cache = None

            else:
                self._internal_setitem__(id, tmpobj)

            if self.sub_split in self.objects[id]._data.keys():
                self.objects[id]._data[self.sub_split]._setParent(self.objects[id])

            self._load_timestamp[id] = os.fstat(fobj.fileno()).st_ctime
        else:
            logger.debug("Didn't Load Job ID: %s" % str(id))

    def _open_xml_file(self, fn):

        fobj = None

        try:
            fobj = open(fn, "r")
        except IOError as x:
            if x.errno == errno.ENOENT:
                # remove index so we do not continue working with wrong information
                try:
                    # remove internal representation
                    self._internal_del__(id)
                    rmrf(os.path.dirname(fn) + ".index")
                except OSError as err:
                    logger.debug("load unlink Error: %s" % str(err))
                    pass
                raise KeyError(id)
            else:
                raise RepositoryError(self, "IOError: " + str(x))
        finally:
            try:
                if os.path.isdir(os.path.dirname(fn)):
                    ld = os.listdir(os.path.dirname(fn))
                    if len(ld) == 0:
                        os.rmdir(os.path.dirname(fn))
                        logger.debug("No job index or data found, removing empty directory: %s" % os.path.dirname(fn))
            except Exception as err:
                logger.debug("load error %s" % str(err))
                pass

        return fobj

    def load(self, ids, load_backup=False):

        # print "load: %s " % str(ids)
        #import traceback
        # traceback.print_stack()

        logger.debug("Loading Repo object(s): %s" % str(ids))


        for id in ids:
            fn = self.get_fn(id)
            if load_backup:
                fn = fn + "~"

            fobj = None

            try:
                fobj = self._open_xml_file(fn)
            except Exception as err:
                logger.debug("Failed to load XML file: %s" % str(fn))
                logger.debug("Error was:\n%s" % str(err))
                raise err

            try:
                self._actually_load_xml(fobj, fn, id, load_backup)
            except RepositoryError as err:
                logger.debug("Repo Exception: %s" % str(err))
                raise err

            except Exception as err:

                if isType(err, XMLFileError):
                    logger.error("XML File failed to load for Job id: %s" % str(id))
                    logger.error("Actual Error was:\n%s" % str(err))

                if load_backup:
                    logger.debug("Could not load backup object #%i: %s %s", id, getName(err), err)
                    import traceback
                    raise InaccessibleObjectError(self, id, err, traceback.format_exc())

                logger.debug("Could not load object #%i: %s", id, str(err))

                # try loading backup
                try:
                    self.load([id], load_backup=True)
                    logger.warning("Object '%s' #%i loaded from backup file - the last changes may be lost.", self.registry.name, id)
                    continue
                except Exception as err2:
                    logger.debug("Exception when loading backup: %s" % str(err2) )

                    if isType(err2, XMLFileError):
                        logger.error("XML File failed to load for Job id: %s" % str(id))
                        logger.error("Actual Error was:\n%s" % str(err2))
                # add object to incomplete_objects
                if not id in self.incomplete_objects:
                    self.incomplete_objects.append(id)
                # remove index so we do not continue working with wrong
                # information
                rmrf(os.path.dirname(fn) + ".index")
                import traceback
                raise InaccessibleObjectError(self, id, err, traceback.format_exc())
            finally:
                fobj.close()

    def delete(self, ids):
        for id in ids:
            # First remove the index, so that it is gone if we later have a
            # KeyError
            fn = self.get_fn(id)
            try:
                rmrf(os.path.dirname(fn) + ".index")
            except OSError as err:
                logger.debug("Delete Error: %s" % str(err))
            self._internal_del__(id)
            rmrf(os.path.dirname(fn))

    def lock(self, ids):
        return self.sessionlock.lock_ids(ids)

    def unlock(self, ids):
        released_ids = self.sessionlock.release_ids(ids)
        if len(released_ids) < len(ids):
            logger.error(
                "The write locks of some objects could not be released!")

    def get_lock_session(self, id):
        """get_lock_session(id)
        Tries to determine the session that holds the lock on id for information purposes, and return an informative string.
        Returns None on failure
        """
        return self.sessionlock.get_lock_session(id)

    def get_other_sessions(self):
        """get_session_list()
        Tries to determine the other sessions that are active and returns an informative string for each of them.
        """
        return self.sessionlock.get_other_sessions()

    def reap_locks(self):
        """reap_locks() --> True/False
        Remotely clear all foreign locks from the session.
        WARNING: This is not nice.
        Returns True on success, False on error."""
        return self.sessionlock.reap_locks()

    def clean(self):
        """clean() --> True/False
        Clear EVERYTHING in this repository, counter, all jobs, etc.
        WARNING: This is not nice."""
        self.shutdown()
        rmrf(self.root)
        self.startup()

