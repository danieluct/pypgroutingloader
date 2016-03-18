"""
Python translation of :
https://github.com/Project-OSRM/osrm-backend/blob/develop/profiles/car.lua

car.lua copyright notice:
Copyright (c) 2016, Project OSRM contributors
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this list
of conditions and the following disclaimer.
Redistributions in binary form must reproduce the above copyright notice, this
list of conditions and the following disclaimer in the documentation and/or
other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

# Car profile
from util.tag_utils import find_access_tag, is_not_empty
from util.duration import parse_duration
from util.config import NUMBER_MATCHER, MPH_MATCHER, SPEED_CONSTANTS_MATCHER


# Begin of globals
barrier_whitelist = { "cattle_grid" : True, "border_control" :True, "checkpoint" : True, "toll_booth" : True, "sally_port" : True, "gate" : True, "lift_gate" : True, "no" : True, "entrance": True }
access_tag_whitelist = { "yes" : True, "motorcar" : True, "motor_vehicle": True, "vehicle" : True, "permissive" : True, "designated" : True, "destination" : True } 
access_tag_blacklist = { "no": True,   "psv": True}
access_tag_restricted = { "destination": True, "delivery": True, "emergency": True, "private": True, "agricultural": True, "forestry": True} 
access_tags = [ "motorcar", "motor_vehicle", "vehicle" ]
access_tags_hierachy = [ "motorcar", "motor_vehicle", "vehicle", "access" ]
service_tag_restricted = { "parking_aisle" : True }
restriction_exception_tags = [ "motorcar", "motor_vehicle", "vehicle" ]

speed_profile = {
  "motorway" : 90,
  "motorway_link" : 45,
  "trunk" : 85,
  "trunk_link" : 40,
  "primary" : 65,
  "primary_link" : 30,
  "secondary" : 55,
  "secondary_link" : 25,
  "tertiary" : 40,
  "tertiary_link" : 20,
  "unclassified" : 25,
  "residential" : 25,
  "living_street" : 10,
  "service" : 15,
  "track" : 5,
  "ferry" : 5,
  "movable" : 5,
  "shuttle_train" : 10,
  "default" : 10
}


# surface/trackype/smoothness
# values were estimated from looking at the photos at the relevant wiki pages

# max speed for surfaces
surface_speeds = {
  "asphalt" : None,  # nil mean no limit. removing the line has the same effect
  "concrete" : None,
  "concrete:plates" : None,
  "concrete:lanes" : None,
  "paved" : None,

  "cement" : 80,
  "compacted" : 80,
  "fine_gravel" : 80,

  "paving_stones" : 60,
  "metal" : 60,
  "bricks" : 60,

  "grass" : 40,
  "wood" : 40,
  "sett" : 40,
  "grass_paver" : 40,
  "gravel" : 40,
  "unpaved" : 40,
  "ground" : 40,
  "dirt" : 40,
  "pebblestone" : 40,
  "tartan" : 40,

  "cobblestone" : 30,
  "clay" : 30,

  "earth" : 20,
  "stone" : 20,
  "rocky" : 20,
  "sand" : 20,

  "mud" : 10
}

# max speed for tracktypes
tracktype_speeds = {
  "grade1" :  60,
  "grade2" :  40,
  "grade3" :  30,
  "grade4" :  25,
  "grade5" :  20
}

# max speed for smoothnesses
smoothness_speeds = {
  "intermediate"    :  80,
  "bad"             :  40,
  "very_bad"        :  20,
  "horrible"        :  10,
  "very_horrible"   :  5,
  "impassable"      :  0
}

# http://wiki.openstreetmap.org/wiki/Speed_limits
maxspeed_table_default = {
  "urban" : 50,
  "rural" : 90,
  "trunk" : 110,
  "motorway" : 130
}

# List only exceptions
maxspeed_table = {
  "ch:rural" : 80,
  "ch:trunk" : 100,
  "ch:motorway" : 120,
  "de:living_street" : 7,
  "ru:living_street" : 20,
  "ru:urban" : 60,
  "ua:urban" : 60,
  "at:rural" : 100,
  "de:rural" : 100,
  "at:trunk" : 100,
  "cz:trunk" : 0,
  "ro:trunk" : 100,
  "cz:motorway" : 0,
  "de:motorway" : 0,
  "ru:motorway" : 110,
  "gb:nsl_single" : (60 * 1609) / 1000,
  "gb:nsl_dual" : (70 * 1609) / 1000,
  "gb:motorway" : (70 * 1609) / 1000,
  "uk:nsl_single" : (60 * 1609) / 1000,
  "uk:nsl_dual" : (70 * 1609) / 1000,
  "uk:motorway" : (70 * 1609) / 1000
}

# these need to be global because they are accesed externaly
u_turn_penalty = 20
traffic_signal_penalty = 2
use_turn_restrictions = True

side_road_speed_multiplier = 0.8

turn_penalty = 10
# Note: this biases right-side driving.  Should be
# inverted for left-driving countries.
turn_bias = 1.2

obey_oneway = True
ignore_areas = True

speed_reduction = 0.8

# modes
mode_normal = 1
mode_ferry = 2
mode_movable_bridge = 3

def get_exceptions(vector):
    for tag in restriction_exception_tags:
        vector.add(tag)

def parse_maxspeed(source,debug=False):
    if debug: print "parsing",source
    if source is None:
        return 0
    n = None
    n_match = NUMBER_MATCHER.match(source)
    if n_match is not None:
        n = float(n_match.group(1))
        if MPH_MATCHER.match(source):
            n = (n * 1609) / 1000
    else:
        # parse maxspeed like FR:urban
        source = source.lower()    
        if not maxspeed_table.has_key(source):
            highway_type = SPEED_CONSTANTS_MATCHER.match(source)
            if (highway_type is not None and 
                maxspeed_table_default.has_key(highway_type.group(0))):
                n = maxspeed_table_default[highway_type]
            if n is None:
                n = 0
        else:
            n = maxspeed_table[source]
    return n

def node_function (node, result):
    # parse access and barrier tags
    access = find_access_tag(node, access_tags_hierachy)  
    result = {'barrier':False, 'traffic_lights':False}
    if is_not_empty(access):
        if  access_tag_blacklist.get(access, False):
            result['barrier'] = True
    else:
        barrier = node.get("barrier", None)      
        if is_not_empty(barrier):
            # make an exception for rising bollard barriers
            rising_bollard = node.has_key("bollard") and (node["bollard"] == "rising")
            
            if (not barrier_whitelist.get(barrier, False)
                and not rising_bollard):
                result['barrier'] = True

    # check if node is a traffic light
    if node.has_key['highway'] and "traffic_signals" == node["highway"]:
        result['traffic_lights'] = True        


class WayResult(object):
    def __init__(self):
        self.forward_speed=-1
        self.backward_speed=-1
        self.roundabout=False
        self.forward_mode=mode_normal
        self.backward_mode=mode_normal
        self.duration = 0
        self.is_startpoint=True
        self.name=None
        self.is_access_restricted=False
        
    def __str__(self):
        return u', '.join(["fspeed: "+str(self.forward_speed),
                          "bspeed: "+str(self.backward_speed),
                          "fmode: "+str(self.forward_mode),
                          "bmode: "+str(self.backward_mode),
                          "roundabout: "+str(self.roundabout),
                          "duration: "+str(self.duration),
                          "restricted: "+str(self.is_access_restricted)])+"\n"
        
def way_function(way,debug=False):
    highway = way.get("highway", None)
    route = way.get("route", None)
    bridge = way.get("bridge", None)
    result = WayResult()

    if not (is_not_empty(highway) or is_not_empty(route) or is_not_empty(bridge)):
        return

    # we dont route over areas
    if ignore_areas and  way.has_key('area') and way['area'] == "yes":
        return

    oneway = way.get('oneway', None)
    if  oneway is not None and "reversible" == way['oneway']:
        return

    if  way.has_key('impassable') and "yes" == way['impassable']:
        return
    
    if  way.has_key('status') and "impassable" == way['status']:
        return

    # Check if we are allowed to access the way
    access = find_access_tag(way, access_tags_hierachy)
    if access_tag_blacklist.get(access, False):
        return

    # handling ferries and piers
    route_speed = speed_profile.get(route, -1)
    if (route_speed > 0):
        highway = route
        duration = parse_duration(way.get('duration',None))
        if duration>-1:
            result.duration = max(duration, 1)

        result.forward_mode = mode_ferry
        result.backward_mode = mode_ferry
        result.forward_speed = route_speed
        if debug: print "route_speed"
        result.backward_speed = route_speed

    bridge_speed = (speed_profile.get(bridge, -1) 
                    if bridge is not None
                    else -1)
    capacity_car = way.get("capacity:car", None)
    if bridge_speed > 0 and (capacity_car is None or capacity_car != 0):
        highway = bridge
        duration = parse_duration(way.get('duration',None))
        if duration>-1:
            result.duration = max(duration, 1)
        result.forward_mode = mode_movable_bridge
        result.backward_mode = mode_movable_bridge
        result.forward_speed = bridge_speed
        if debug: print "bridge_speed"
        result.backward_speed = bridge_speed

    # leave early of this way is not accessible
    if "" == highway:
        return

    if result.forward_speed == -1:
        highway_speed = speed_profile.get(highway, None)        
        max_speed = parse_maxspeed(way.get("maxspeed", None),debug)
        if debug: print "parsed maxspeed", max_speed
        # Set the avg speed on the way if it is accessible by road class
        if highway_speed is not None:
            if max_speed  is not None and max_speed > highway_speed:
                result.forward_speed = max_speed
                if debug: print "max_speed", max_speed
                result.backward_speed = max_speed
                # max_speed = 9999
            else:
                result.forward_speed = highway_speed
                if debug: print "hihgway_speed"
                result.backward_speed = highway_speed
        else:
            # Set the avg speed on ways that are marked accessible
            if access_tag_whitelist.get(access, False):
                result.forward_speed = speed_profile["default"]
                if debug: print "speed_profile"
                result.backward_speed = speed_profile["default"]

        if max_speed is None or 0 == max_speed:
            max_speed = 160
        result.forward_speed = min(result.forward_speed, max_speed)
        if debug: print "min_speed",result.forward_speed, max_speed
        result.backward_speed = min(result.backward_speed, max_speed)

    if -1 == result.forward_speed and -1 == result.backward_speed:
        print "ERROR: access utterly forbidden"
        return

    # reduce speed on special side roads
    if way.has_key("side_road"):
        if way["side_road"] in ("yes", "rotary"):
            result.forward_speed = result.forward_speed * side_road_speed_multiplier
            if debug: print "side_road"
            result.backward_speed = result.backward_speed * side_road_speed_multiplier
    
    # reduce speed on bad surfaces
    surface = way.get("surface", None)
    tracktype = way.get("tracktype", None)
    smoothness = way.get("smoothness", None)

    if surface is not None and surface_speeds.has_key(surface) :
        if surface_speeds[surface] is not None:
            result.forward_speed = min(surface_speeds[surface], result.forward_speed)
            if debug: print "surface_speed",surface_speeds[surface], result.forward_speed
            result.backward_speed = min(surface_speeds[surface], result.backward_speed)
        
    if tracktype is not None and tracktype_speeds.has_key(tracktype):
        result.forward_speed = min(tracktype_speeds[tracktype], result.forward_speed)
        if debug: print "track_speed"
        result.backward_speed = min(tracktype_speeds[tracktype], result.backward_speed)
        
    if smoothness is not None and smoothness_speeds.has_key(smoothness):
        result.forward_speed = min(smoothness_speeds[smoothness], result.forward_speed)
        if debug: print "smoothness_speed"
        result.backward_speed = min(smoothness_speeds[smoothness], result.backward_speed)

    # parse the remaining tags
    name = way.get("name", None)
    ref = way.get("ref", None)
    junction = way.get("junction", None)
    # barrier = way.get("barrier","")
    # cycleway = way.get("cycleway","")
    service = way.get("service", None)

    # Set the name that will be used for instructions
    has_ref = is_not_empty(ref)
    has_name = is_not_empty(name)

    if has_name and has_ref:
        result.name = name + " (" + ref + ")"
    elif has_ref:
        result.name = ref
    elif has_name:
        result.name = name
    # else:
    #    result.name = highway  # if no name exists, use way type

    if junction is not None and "roundabout" == junction:
        result.roundabout = True

    # Set access restriction flag if access is allowed under certain restrictions only
    if access != "" and access_tag_restricted.get(access, False):
        result.is_access_restricted= True

    # Set access restriction flag if service is allowed under certain restrictions only
    if is_not_empty(service) and service_tag_restricted.get(service, False):
        result.is_access_restricted= True

    # Set direction according to tags on way
    if obey_oneway:
        if oneway is not None:
            if oneway == "-1":
                result.forward_mode = 0
            elif (oneway in ("yes", "1", "True") 
                  or result.roundabout
                  or (highway is not None and
                       highway in ("motorway_link", "motorway") 
                      and oneway != "no")):
                result.backward_mode = 0
        elif (result.roundabout  or 
              (highway is not None and highway in ("motorway_link", "motorway"))):
            result.backward_mode = 0


    # Override speed settings if explicit forward/backward maxspeeds are given
    maxspeed_forward = parse_maxspeed(way.get("maxspeed:forward", None),debug)
    maxspeed_backward = parse_maxspeed(way.get("maxspeed:backward", None),debug)
    if maxspeed_forward > 0:
        if 0 != result.forward_mode and 0 != result.backward_mode:
            result.backward_speed = result.forward_speed
        result.forward_speed = maxspeed_forward
        if debug: print "max_speed_forward"

    if maxspeed_backward > 0:
        result.backward_speed = maxspeed_backward

    # Override speed settings if advisory forward/backward maxspeeds are given
    advisory_speed = parse_maxspeed(way.get("maxspeed:advisory", None),debug)
    advisory_forward = parse_maxspeed(way.get("maxspeed:advisory:forward", None),debug)
    advisory_backward = parse_maxspeed(way.get("maxspeed:advisory:backward", None),debug)
    # apply bi-directional advisory speed first
    if advisory_speed > 0:
        if 0 != result.forward_mode:
            result.forward_speed = advisory_speed
            if debug: print "advisory_speed"
        if 0 != result.backward_mode:
            result.backward_speed = advisory_speed
    if advisory_forward > 0:
        if 0 != result.forward_mode and 0 != result.backward_mode:
            result.backward_speed = result.forward_speed
        result.forward_speed = advisory_forward
        if debug: print "advisory_forward"
    if advisory_backward > 0:
        result.backward_speed = advisory_backward

    width = 9999
    lanes = 9999
    if result.forward_speed > 0 or result.backward_speed > 0:
        width_string = way.get("width", None)
        if width_string is not None and NUMBER_MATCHER.match(width_string) is not None:
            width = float(NUMBER_MATCHER.match(width_string).group(1))
        lanes_string = way.get("lanes", None)
        if lanes_string is not None and NUMBER_MATCHER.match(lanes_string) is not None:
            lanes = float(NUMBER_MATCHER.match(lanes_string).group(1))

    is_bidirectional = result.forward_mode != 0 and result.backward_mode != 0

    # scale speeds to get better avg driving times
    if result.forward_speed > 0:
        scaled_speed = result.forward_speed * speed_reduction + 11
        penalized_speed = 9999
        if width <= 3 or (lanes <= 1 and is_bidirectional):
            penalized_speed = result.forward_speed / 2.
        result.forward_speed = min(penalized_speed, scaled_speed)
        if debug: print "penalized_speed",penalized_speed, scaled_speed

    if result.backward_speed > 0:
        scaled_speed = result.backward_speed * speed_reduction + 11
        penalized_speed = 9999
        if width <= 3 or (lanes <= 1 and is_bidirectional):
            penalized_speed = result.backward_speed / 2.
        result.backward_speed = min(penalized_speed, scaled_speed)
        if debug: print "scaled_speed",penalized_speed, scaled_speed

    result.is_startpoint = (result.forward_mode == mode_normal 
                               or result.backward_mode == mode_normal)
    return result


def turn_function(angle):
    # compute turn penalty as angle^2, with a left/right bias
    k = turn_penalty / (90.0 * 90.0)
    if angle >= 0:
        return angle * angle * k / turn_bias
    else:
        return angle * angle * k * turn_bias
