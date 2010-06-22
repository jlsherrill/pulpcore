#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2010 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.

import functools
import os
import sys
import traceback
import urllib

try:
    import json
except ImportError:
    import simplejson as json
    
import pymongo.json_util 
import web

from juicer import http
from juicer.queues import fifo
from pulp.tasking.task import Task, TaskModel, task2model


class JSONController(object):
    """
    Base controller class with convenience methods for JSON serialization
    """
    @staticmethod
    def error_handler(method):
        """
        Controller class method wrapper that catches internal errors and reports
        them as JSON serialized trace back strings
        """
        @functools.wraps(method)
        def report_error(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except Exception:
                exc_info = sys.exc_info()
                tb_msg = ''.join(traceback.format_exception(*exc_info))
                return self.internal_server_error(tb_msg)
        return report_error
    
    def params(self):
        """
        JSON decode the objects in the requests body and return them
        """
        return json.loads(web.data())
    
    def filters(self):
        """
        Fetch any arguments passed on the url
        """
        return web.input()

    def _output(self, data):
        """
        JSON encode the response and set the appropriate headers
        """
        http.header('Content-Type', 'application/json')
        return json.dumps(data, default=pymongo.json_util.default)
    
    def ok(self, data):
        """
        Return an ok response.
        @type data: mapping type
        @param data: data to be returned in the body of the response
        @return: JSON encoded response
        """
        http.status_ok()
        return self._output(data)
    
    def created(self, location, data):
        """
        Return a created response.
        @type location: str
        @param location: URL of the created resource
        @type data: mapping type
        @param data: data to be returned in the body of the response
        @return: JSON encoded response
        """
        http.status_created()
        http.header('Location', location)
        return self._output(data)
    
    def not_found(self, msg=None):
        """
        Return a not found error.
        @type msg: str
        @param msg: optional error message
        @return: JSON encoded response
        """
        http.status_not_found()
        return self._output(msg)
        
    def method_not_allowed(self, msg=None):
        """
        Return a method not allowed error.
        @type msg: str
        @param msg: optional error message
        @return: JSON encoded response
        """
        http.status_method_not_allowed()
        return None
    
    def not_acceptable(self, msg=None):
        """
        Return a not acceptable error.
        @type msg: str
        @param msg: optional error message
        @return: JSON encoded response
        """
        http.status_not_acceptable()
        return self._output(msg)
    
    def conflict(self, msg=None):
        """
        Return a conflict error.
        @type msg: str
        @param msg: optional error message
        @return: JSON encoded response
        """
        http.status_conflict()
        return self._output(msg)
    
    def internal_server_error(self, msg=None):
        """
        Return an internal server error.
        @type msg: str
        @param msg: optional error message
        @return: JSON encoded response
        """
        http.status_internal_server_error()
        return self._output(msg)


class AsyncController(JSONController):
    """
    Base controller class with convenience methods for executing asynchronous
    tasks.
    """
    def start_task(self, func, *args, **kwargs):
        """
        Execute the function and its arguments as an asynchronous task.
        @param func: python callable
        @param args: positional arguments for func
        @param kwargs: key word arguments for func
        @return: TaskModel instance
        """
        task = Task(func, *args, **kwargs)
        fifo.enqueue(task)
        return task2model(task)
    
    def _status_path(self, id):
        """
        Construct a URL path that can be used to poll a task's status
        A status path is constructed as follows:
        /<collection>/<object id>/<action>/<action id>/
        A GET request sent to this path will get a JSON encoded status object
        """
        parts = web.ctx.path.split('/')
        if parts[-2] == id:
            path = web.ctx.path
        else:
            path = os.path.normpath(os.path.join(web.ctx.path, id)) # cleanly concatenate the current path with the id
            path = web.http.url(path)                               # add the application prefix
            path += '/'                                             # all urls are paths, so need a trailing '/'
        return urllib.pathname2url(path) # make sure the path is properly encoded
    
    def task_status(self, id):
        """
        Get the current status of an asynchronous task.
        @param id: task id
        @return: TaskModel instance
        """
        status = fifo.status(id)
        if isinstance(status, TaskModel):
            status.update({'status_path': self._status_path(id)})
        return status
    
    def accepted(self, status):
        """
        Return an accepted response with status information in the body.
        @param id: task id
        @return: JSON encoded response
        """
        http.status_accepted()
        status.update({'status_path': self._status_path(status['id'])})
        return self._output(status)