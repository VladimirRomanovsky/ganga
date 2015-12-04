# import unittest2 for python 2.6
try:
    import unittest2 as unittest
except ImportError:
    import unittest


class TestThreadPoolQueueMonitor(unittest.TestCase):
    """
    Test the ThreadPoolQueueMonitor objects
    """
    # TODO: Default construction requires config available
    # def test_create_threadpoolqueuemonitor_def(self):
    #     """
    #     Check you can create a ThreadPoolQueueMonitor object
    #     """
    #     from Ganga.Core.GangaThread.WorkerThreads.ThreadPoolQueueMonitor import ThreadPoolQueueMonitor
    #     e = ThreadPoolQueueMonitor()
    #     self.assertIsInstance(e, ThreadPoolQueueMonitor)

    # TODO: Cannot import the module as getConfig is a default argument
    # def test_create_threadpoolqueuemonitor(self):
    #      """
    #      Check you can create a ThreadPoolQueueMonitor object
    #      """
    #      from Ganga.Core.GangaThread.WorkerThreads.ThreadPoolQueueMonitor import ThreadPoolQueueMonitor
    #      from Ganga.Core.GangaThread.WorkerThreads.WorkerThreadPool import WorkerThreadPool
    #
    #      p = WorkerThreadPool(5, "testthread_")
    #      e = ThreadPoolQueueMonitor(user_threadpool = p, monitoring_threadpool=p)
    #      self.assertIsInstance(e, ThreadPoolQueueMonitor)
