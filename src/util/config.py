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
import re
import os.path

REQUIRED_CONNECTION_PROPERTIES = set(['host', 'port', 'database', 'user',
                                      'password'])
GDAL_CONNECTION_PROP_MAP = {'host':'', 'port':'', 'dbname':'database', 'user':'',
                                      'password':''}
FALSE_VALUES_SET = set(['0', 'false', 'no'])
TRUE_VALUES_SET = set(['1', 'true', 'yes'])
REVERSE_VALUES_SET = set(['-1', 'reverse'])

ONEWAY_FORWARD = 'FT'
ONEWAY_BACKWARD = 'TF'
BOTH_WAYS = 'NO'

NOT_AREA = 0
MAYBE_AREA = 1
SURE_AREA = 2

NUMBER_MATCHER = re.compile('(-?\d+(\.\d*)?).*')
MPH_MATCHER = re.compile('.*mp/?h')
SPEED_CONSTANTS_MATCHER = re.compile('[a-zA-Z][a-zA-Z]:\w+')

class Configuration:    
    
    def __init__(self,
                 conf_path=os.path.join(os.path.abspath(os.path.dirname(__file__)),
                                         '../conf/')):
        self.set_dictionary = {}
        self.conf_path = conf_path
        self.speeds = Speeds(os.path.join(self.conf_path,
                                          'speed_constants.conf'))
        self.barriers = BarrierCosts(os.path.join(self.conf_path,
                                          'costs/point_barrier_costs.conf'))
        self.access = AccessCosts(os.path.join(self.conf_path,
                                          'costs/access_costs.conf'))
        self.hierarchy = VehicleHierarchy(os.path.join(self.conf_path,
                                          'vehicle_hierarchy.conf'))
        self.conf_mapping = {
                             'AREA_KEYSET':'area_keys',
                             'IGNORE_LINES_KEYSET':'ignored_way_keys',
                             'CLOSED_LINE_KEYSET':'circular_way_keys',
                             'SPEED_LIMIT_KEYSET':'',
                             'ALLOWED_WAY_TAGS':'routable_way_keys',
                             'HIGHWAY_PROPS_TAGS':'way_properties_keys',
                             'SPECIFIC_RESTRICTION_KEYS':'relevant_restriction_keys',
                             'ROUTE_WAY_HELPFUL_TAGS':'',
                             'RESTRICTION_HELPFUL_TAGS':'',
                             'OTHERWAYS_KEYSET':'',
                             'ALLOWED_HIGHWAY_VALUES':'routable_highway_values',
                             'ALLOWED_JUNCTION_VALUES':'routable_junction_values',
                             'ALLOW_BARRIER_VALUES':'routed_barrier_values',
                             'ALLOWED_VEHICLES':'allowed_vehicle_keys',
                             'SPEED_CONSTANTS':'speed_constants'
                             }
    
    def _load_config_as_set(self, filepath):
        config_set = set()
        
        with open(filepath, 'r') as f:
            for line in f:
                value = line.strip()
                if value[0] != '#':
                    config_set.add(value)
        return config_set
    
    def get_constants_as_set(self, key):
        if not self.set_dictionary.has_key(key):
            if not self.conf_mapping.has_key(key):
                raise Exception("unknown configuration keyword")
            else:
                self.set_dictionary[key] = self._load_config_as_set(
                                             os.path.join(self.conf_path,
                                                           self.conf_mapping[key] + 
                                                                    ".conf"))        
        return self.set_dictionary[key]
    
    def get_speed_as_number(self, keyvals, default=50):
        values = []
        for key in self.get_constants_as_set('ALLOWED_VEHICLES'):
            exception_key = 'maxspeed:' + key
            if keyvals.has_key(exception_key):
                values.append(self.speeds.compute_speed(exception_key, keyvals))
        if len(values) > 0:
            return min(values)
        
        if keyvals.has_key('maxspeed'):
            return self.speeds.compute_speed('maxspeed', keyvals, default)
        else:
            return default
        
    def get_barrier_cost(self, keyval):
        basic_cost = self.barriers.compute_cost(keyval.get('barrier'))
        if basic_cost is None:
            return None
        
        if basic_cost < 0:
            return 99999
        
        traffic_allowed = self.get_actual_access(keyval,
                                             self.barriers.compute_default_access(keyval))
        basic_cost *= self.access.get_cost_multiplier(traffic_allowed)
        if basic_cost < 0:
            return 99999
        else:
            return basic_cost
        
    def get_access_cost_multiplier(self, val):
        if val.find(';') >= 0:
            values = [x.strip() for x in val.split(';')]
        else:
            values = [val]
        
        costs = [self.access.get_cost_multiplier(x) for x in values]
        if -1 in costs:
            return -1
        else:
            return max(costs)
        
    def get_useful_properties(self, keyvals):
        properties = {}
        found_tags = 0
        for n2know in self.get_constants_as_set('HIGHWAY_PROPS_TAGS').intersection(keyvals.keys()):
            properties[n2know] = keyvals[n2know]
            found_tags += 1
        return properties
    
    def is_routable_way(self, keyval):
        return not self.get_constants_as_set('ALLOWED_WAY_TAGS').isdisjoint(keyval.keys())
    
    def is_routable_highway(self, keyval):
        if keyval.has_key('highway'):
            return keyval['highway'] in self.get_constants_as_set('ALLOWED_HIGHWAY_VALUES')
        return False
    
    def is_routable_junction(self, keyval):
        if keyval.has_key('junction'):
            return keyval['junction'] in self.get_constants_as_set('ALLOWED_JUNCTION_VALUES')
        return False
    
    def is_adequate_ferry(self, keyval, default=True):
        if not keyval.has_key('route') and not keyval.has_key('ferry'):
            return False
        if 'ferry' not in keyval['route'] and not keyval.has_key('ferry'):
            return False
        pass_keys = self.get_constants_as_set('ALLOWED_VEHICLES').intersection(keyval.keys())    
        for key in pass_keys:
            if keyval[key] in FALSE_VALUES_SET:
                return False
        return True
    
    def get_parent_vehicle(self, value):
        return self.hierarchy.get_parent(value)
    
    def get_actual_access(self, keyval, actual_access='yes'):
        if keyval.has_key('access'):
            actual_access = keyval['access']
        
        allowed_vehicles = self.get_constants_as_set('ALLOWED_VEHICLES')
        for vehicle in allowed_vehicles:
            for actual_v in self.hierarchy.get_hierarchy(vehicle):
                if keyval.has_key(actual_v):
                    actual_access = keyval[actual_v]
                    break
        return actual_access
    
    
    def get_route_direction(self, keyval):
        # print keyval
        exceptions = {BOTH_WAYS:0, ONEWAY_BACKWARD:0, ONEWAY_FORWARD:0}
        for key in self.get_constants_as_set('ALLOWED_VEHICLES'):
            exception_key = 'oneway:' + key
            if keyval.has_key(exception_key):
                # print exception_key,keyval[exception_key]
                if keyval[exception_key] in FALSE_VALUES_SET:
                    exceptions[BOTH_WAYS] += 1
                elif keyval[exception_key] in  REVERSE_VALUES_SET:
                    exceptions[ONEWAY_BACKWARD] += 1
                else:
                    exceptions[ONEWAY_FORWARD] += 1
        most_common = max(exceptions.iteritems(), key=lambda x:x[1])
        if most_common[1] > 0:
            # print '*',most_common,exceptions
            # raw_input()
            return most_common[0]
        
        
        for key in self.get_constants_as_set('ALLOWED_VEHICLES'):
            direction = None
            if keyval.has_key(key + ":forward"):
                if direction is None:
                    direction = 0
                if keyval[key + ":forward"] in FALSE_VALUES_SET:
                    direction -= 1
                else:
                    direction += 1
            if keyval.has_key(key + ":backward"):
                if direction is None:
                    direction = 0
                if keyval[key + ":backward"] in FALSE_VALUES_SET:
                    direction += 1
                else:
                    direction -= 1
            if direction is not None:
                if direction > 0:
                    exceptions[ONEWAY_FORWARD] += 1
                elif direction == 0:
                    exceptions[BOTH_WAYS] += 1
                elif direction < 0 :
                    exceptions[ONEWAY_BACKWARD] += 1
                
        most_common = max(exceptions.iteritems(), key=lambda x:x[1])
        if most_common[1] > 0:
            # print '**',most_common
            # raw_input()
            return most_common[0], exceptions    
            
        if keyval.has_key('oneway'):
            # print '***',keyval['oneway']
            if keyval['oneway'] in FALSE_VALUES_SET:
                # print "both"
                # raw_input()
                return BOTH_WAYS
            elif keyval['oneway'] in REVERSE_VALUES_SET:
                # print "back"
                # raw_input()
                return ONEWAY_BACKWARD
            else:
                # print "front"
                # raw_input()
                return ONEWAY_FORWARD
            
        if keyval.has_key('junction') and 'roundabout' in keyval['junction']:
            # print "*front"
            # raw_input()
            return ONEWAY_FORWARD
        
        # print "<<<both"
        # raw_input()
        return BOTH_WAYS
        
    def is_area(self, keyval):
        if keyval.has_key('area'):
            if keyval['area'] in FALSE_VALUES_SET:
                return NOT_AREA
            else:
                return SURE_AREA
                
        if (not self.get_constants_as_set('AREA_KEYSET').isdisjoint(keyval.keys())
            and not keyval.has_key('highway')):
            return SURE_AREA
        
        return MAYBE_AREA
    
    def is_excepted(self, keyval):
        if keyval.has_key('except'):
            excepted = keyval['except'].split(';')
            allowed_vehicles = self.get_constants_as_set('ALLOWED_VEHICLES')
            for vehicle in allowed_vehicles:
                for actual_v in self.hierarchy.get_hierarchy(vehicle):
                    if actual_v in excepted:
                        return True
        return False
    
    def is_valid_restriction(self, relation_type):
        if relation_type == 'restriction':
            return True
        allowed_vehicles = self.get_constants_as_set('ALLOWED_VEHICLES')
        for vehicle in allowed_vehicles:
            for actual_v in self.hierarchy.get_hierarchy(vehicle):
                if relation_type == 'restriction:' + actual_v:
                    return True
        return False
    
    def get_actual_restriction_type(self, keyval):
        allowed_vehicles = self.get_constants_as_set('ALLOWED_VEHICLES')
        for vehicle in allowed_vehicles:
            for actual_v in self.hierarchy.get_hierarchy(vehicle):
                if keyval.has_key('restriction:' + actual_v):
                    return keyval['restriction:' + actual_v]       
        if keyval.has_key('restriction'):
            return keyval['restriction']
        return None
    
class AccessCosts(object):
    def __init__(self, filepath="access_costs.conf"):
        self.access_costs = {}
        
        with open(filepath, 'r') as f:
            ignore_line = True
            for line in f:
                if ignore_line:
                    ignore_line = False
                    continue
                elems = line.strip().split('\t')
                # print elems
                self.access_costs[elems[0]] = float(elems[1])
                
    def get_cost_multiplier(self, value):
        if self.access_costs.has_key(value):
            return self.access_costs[value]
        else:
            # print 'unknown access value',value
            return -1
        
class VehicleHierarchy(object):
    def __init__(self, filepath="vehicle_hierarchy.conf"):
        self.hierarchy = {}
        
        with open(filepath, 'r') as f:
            for line in f:
                elems = line.strip().split('\t')
                if len(elems) > 1:
                    self.hierarchy[elems[0]] = elems[1]
                else:
                    self.hierarchy[elems[0]] = None
                    
        self.full_hierarchy = {}
        for key in self.hierarchy.keys():
            full_h = [key]
            par = self.get_parent(key)
            while par is not None:
                full_h.append(par)
                par = self.get_parent(par)
            self.full_hierarchy[key] = full_h
                
    
    def get_parent(self, value):
        if self.hierarchy.has_key(value):
            return self.hierarchy[value]
        return None
    
    def get_hierarchy(self, value):
        return self.full_hierarchy.get(value, [])

class BarrierCosts(object):
    def __init__(self, filepath="point_barrier_costs.conf"):
        self.barrier_costs = {}
        
        with open(filepath, 'r') as f:
            ignore_line = True
            for line in f:
                if ignore_line:
                    ignore_line = False
                    continue
                elems = line.strip().split('\t')
                # print elems
                self.barrier_costs[elems[0]] = (float(elems[1]), elems[2])
                
    def compute_cost(self, key):
        if self.barrier_costs.has_key(key):
            return self.barrier_costs[key][0]
        else:
            return None
        
    def compute_default_access(self, keyval):
        if self.barrier_costs.has_key(keyval['barrier']):
            if (keyval['barrier'] == 'bollard' and
                keyval.has_key('bollard') and
                'rising' in keyval.get('bollard')):
                return 'yes'
            return self.barrier_costs[keyval['barrier']][1]
        else:
            return 'yes'
                

class Speeds(object):
    '''
    classdocs
    '''

    def __init__(self, filepath="speed_constants.conf"):
        self.MPH_PATTERN = re.compile("^([0-9]+) ?mph$")
        self.known_limits = {}
        
        with open(filepath, 'r') as f:
            ignore_line = True
            for line in f:
                if ignore_line:
                    ignore_line = False
                    continue
                elems = line.strip().split('\t')
                self.known_limits[elems[0]] = {}
                if ';' not in elems[1]:
                    self.known_limits[elems[0]]['KMPH:default'] = self._to_kmph(elems[1])
                else:
                    for bits in elems[1].split(';'):
                        key, val = bits.split('#')
                        if len(key) == 0:
                            self.known_limits[elems[0]]['KMPH:default'] = self._to_kmph(val)
                        else:
                            self.known_limits[elems[0]][key] = self._to_kmph(val)

    def _milesph_to_kmph(self, value):
        return int(value * 1.609344)

    def _to_kmph(self, string):
        test_mph = self.MPH_PATTERN.match(string.lower())
        if test_mph is not None:
            return self._milesph_to_kmph(int(test_mph.group(1)))
        else:
            return int(string)

    def compute_speed(self, speed_tag, keyvals, default=50):
        orig_speed_str = keyvals[speed_tag]
        max_speeds = set()
        for speed_string in  (y.strip() for y in keyvals[speed_tag].split(';')):
            if speed_string.isdigit():
                max_speeds.add(int(speed_string))
            else:
                try:
                    max_speeds.add(self._to_kmph(speed_string))
                    # print "not exception",speed_string,self._to_kmph(speed_string)
                except Exception:
                    # print "exception",speed_string
                    if speed_string in self.known_limits.keys():
                        speed_dic = self.known_limits[speed_string]
                        if len(speed_dic.keys()) > 1:
                            intersection = set(speed_dic.keys()).intersection(keyvals.keys())
                            if len(intersection) > 0:
                                max_speeds.add(min([speed_dic[x] for x in intersection]))
                            else:
                                max_speeds.add(speed_dic['KMPH:default'])
                        else:
                                max_speeds.add(speed_dic['KMPH:default'])
                    else:
                        print 'unknown speed:', speed_string
        if len(max_speeds) == 0:
            print speed_string, keyvals
            max_speeds.add(default)
        if len(max_speeds) > 1:
            print orig_speed_str, ">", max_speeds
        return min(max_speeds)

def load_connection_info_from_config(config):
    missing_keys = []
    section = 'Target Postgres'
    connection_info = { 'host':'localhost',
                       'port':5432,
                       'user':'postgres',
                       'password':'postgres'}
    if config.has_section(section):        
        for key in REQUIRED_CONNECTION_PROPERTIES:
            try:
                connection_info[key] = config.get(section, key)
            except Exception as e:
                print e
                missing_keys.append(key)
    return (connection_info, missing_keys)

def load_connection_info_from_gdal_string(gdal_string):
    connection_info = { 'host':'localhost',
                   'port':5432,
                   'user':'postgres',
                   'password':'postgres'}
    if gdal_string.startswith('PG:'):
        gdal_string = gdal_string[4:-1]
        
    if not gdal_string:
        return None
    properties = dict([_property.split('=') 
                       for _property in gdal_string.split(' ')])
    
    for key in GDAL_CONNECTION_PROP_MAP.keys():
        if properties.has_key(key):
            if not GDAL_CONNECTION_PROP_MAP[key]:
                connection_info[key] = properties[key].strip("'")
            else:
                connection_info[GDAL_CONNECTION_PROP_MAP[key]] = properties[key].strip("'")       
    
    return connection_info
