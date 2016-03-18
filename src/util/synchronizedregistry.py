'''
    Copyright (C) 2016  daniel.urda

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import multiprocessing

class SynchronizedRegistry(object):
    def __init__(self):
        self.lock = multiprocessing.Lock()
        self._dict = {}
        
    def put(self, key, value):
        with self.lock:
            if not self._dict.has_key(key):
                self._dict[key] = []
            self._dict[key].append(value)
        
    def get(self, key):
        return self._dict[key]
    
    def set(self, key, value):
        with self.lock:
            self._dict[key] = value
    
    def get_backing_dict(self):
        return self._dict
