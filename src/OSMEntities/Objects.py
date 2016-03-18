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
from util.geom import get_angle_between_points
from util.tag_utils import pair_as_string
       
class RoutingNode(object):
    '''
    classdocs
    '''

    def __init__(self, osm_id):
        self._osm_id = osm_id
        self.segments=set()
        self.ways=set()
        
    def get_edges(self):
        return self.segments
                
    def use_segment(self,segment):
        self.segments.add(segment)
        
    def get_id(self):
        return self._osm_id
    
    def get_db_id(self):
        return self._db_id
    
    def set_db_id(self, _id):
        self._db_id = _id

    def use(self, way):
        self.ways.add(way)    
   
class RoutingRestriction(object):
    '''
    classdocs
    '''

    def __init__(self, osm_id, is_point=False):
        self._osm_id = osm_id
        self._from = []
        self._to = []
        self._via_ways = []
        self._via_nodes = []
        self._properties = {}
        self._commons = []
        self._is_point = is_point
        if is_point:
            self.add_property('restriction','barrier')
        self._cost=99999
        self._source_edges=set()
        
    def validate_ways(self,ways):
        idx = 0
        while idx<len(self._from):
            if not ways.has_key(self._from[idx]):
                del self._from[idx]
                idx -=1
            else:
                self._from[idx]=ways[self._from[idx]]
            idx+=1
            
        idx = 0
        while idx<len(self._to):
            if not ways.has_key(self._to[idx]):
                del self._to[idx]
                idx -=1
            else:
                self._to[idx]=ways[self._to[idx]]
            idx+=1
        
        return self.seems_valid()
        
    def get_properties(self):
        return self._properties
        
    def set_cost(self,cost):
        self._cost=cost
        
    def get_first_via_node(self):
        return self._via_nodes[0]
        
    def get_all_common_segments(self, node_map):
        local_commons = {}
        for ff in self._from:
            for tt in self._to:
                for common in self.get_common_segments(ff, tt, node_map):
                    if not local_commons.has_key(common.via_node):
                        local_commons[common.via_node]=[]
                    local_commons[common.via_node].append(common)
        return local_commons
    
    def get_as_proper_restrictions(self, node_map):
        proper_restrictions = {}
        if not self._is_point:
            local_commons = self.get_all_common_segments(node_map)
            if len(self._via_nodes)>0:
                first_via_node = self.get_first_via_node()
                if not local_commons.has_key(first_via_node):
                    print "WARNING:",self._osm_id,"via node declared",first_via_node,"; should be",local_commons.keys()
                else:
                    proper_restrictions[first_via_node] = local_commons[first_via_node]
            else:
                print "WARNING:",self._osm_id,"no via node declared; found",local_commons.keys()
                for keye,valz in local_commons.iteritems():
                        proper_restrictions[keye] =valz
        else:
            local_commons = []
            from_vals=len(self._from)
            for ii in range(0,from_vals):
                ff = self._from[ii]
                for ji in range(ii,from_vals):
                    tt = self._from[ji]
                    for common in self.get_common_segments_on_node(ff,tt,self.get_first_via_node()):
                        local_commons.append(common)
            if len(local_commons)>2:
                print "barrier",common.via_node,"affects more than two segments"
                #for comm in local_commons:
                #    print comm
                #print "-----"
            proper_restrictions[self.get_first_via_node()] = local_commons
            
        return proper_restrictions
    
    def add_source_segment(self, segm):        
        self._source_edges.add(segm)
        if self._is_point:
            parent_id = segm.parent.get_id()
            if parent_id not in self._from:
                self._from.append(parent_id)
        
    def get_common_segments_on_node(self, from_, to_, node_id):
        commons =[]
        known_commons=set()
        for segm1 in from_.get_segments():
            for segm2 in to_.get_segments():
                if (segm1.get_db_id()!=segm2.get_db_id() and 
                    (segm2.get_db_id(),segm1.get_db_id()) not in known_commons):
                    if segm1.get_head()==node_id:
                        if (segm2.get_head()==node_id 
                            or segm2.get_tail()==node_id):
                            commons.append(ProperRestriction(segm1,
                                                   segm2,
                                                   node_id,
                                                   self._properties['restriction'],
                                                   self))
                            commons.append(ProperRestriction(segm2,
                                                   segm1,
                                                   node_id,
                                                   self._properties['restriction'],
                                                   self))
                            known_commons.add((segm1.get_db_id(),segm2.get_db_id()))
                    elif segm1.get_tail()==node_id:
                        if (segm2.get_head()==node_id 
                            or segm2.get_tail()==node_id):
                            commons.append(ProperRestriction(segm1,
                                                   segm2,
                                                   node_id,
                                                   self._properties['restriction'],
                                                   self))
                            commons.append(ProperRestriction(segm2,
                                                   segm1,
                                                   node_id,
                                                   self._properties['restriction'],
                                                   self))
                            known_commons.add((segm1.get_db_id(),segm2.get_db_id()))
        return commons
    
    def get_common_segments(self, from_, to_, node_map):
        commons =[]
        for segm1 in from_.get_segments():
            for segm2 in to_.get_segments():
                #print "segmenti",segm1, segm2
                if segm1.get_head() == segm2.get_head():
                    #print "cap-cap"
                    proper = ProperRestriction(segm1,
                                               segm2,
                                               segm1.get_head(),
                                               self._properties['restriction'],
                                               self)
                    proper.set_angle(get_angle_between_points(
                            node_map.get(segm1.get_node_id_near_end(0)),
                            node_map.get(segm1.get_head()),
                            node_map.get(segm2.get_node_id_near_end(0))))
                    commons.append(proper)
                if segm1.get_head() == segm2.get_tail():
                    #print "cap-coada"
                    proper = ProperRestriction(segm1,
                                               segm2,
                                               segm1.get_head(),
                                               self._properties['restriction'],
                                               self)
                    proper.set_angle(get_angle_between_points(
                            node_map.get(segm1.get_node_id_near_end(0)),
                            node_map.get(segm1.get_head()),
                            node_map.get(segm2.get_node_id_near_end(-1))))
                    commons.append(proper)
                if segm1.get_tail() == segm2.get_head():
                    #print "coada-cap"
                    proper = ProperRestriction(segm1,
                                               segm2,
                                               segm1.get_tail(),
                                               self._properties['restriction'],
                                               self)
                    proper.set_angle(get_angle_between_points(
                            node_map.get(segm1.get_node_id_near_end(-1)),
                            node_map.get(segm1.get_tail()),
                            node_map.get(segm2.get_node_id_near_end(0))))
                    commons.append(proper)
                if segm1.get_tail() == segm2.get_tail():
                    #print "coada-coada"
                    proper = ProperRestriction(segm1,
                                               segm2,
                                               segm1.get_tail(),
                                               self._properties['restriction'],
                                               self)
                    proper.set_angle(get_angle_between_points(
                            node_map.get(segm1.get_node_id_near_end(-1)),
                            node_map.get(segm1.get_tail()),
                            node_map.get(segm2.get_node_id_near_end(-1))))
                    commons.append(proper)
        return commons
                    

    def add_end_member(self, _type, way):
        if _type == 'from':            
            self._from.append(way)
        elif _type == 'to':
            self._to.append(way)
        else:
            raise Exception("unknown end type")

    def add_via_member(self, _type, member):
        if _type == "node":
            self._via_nodes.append(member)
            #member.use()
        elif _type == "way":
            self._via_ways.append(member)
        else:
            raise Exception("unknown via member type")

    def seems_valid(self):
        return len(self._from) > 0 and (self._is_point or len(self._to) > 0)

    def add_property(self, key, value):
        if self._properties.has_key(key):
            print ("WARNING: key", key, "already exists with value",
                   self._properties[key], ". Will replace with", value)
        self._properties[key] = value
        
    def get_common_ends(self):
        return set(self._from).intersection(set(self._to))
        
class ProperRestriction(object):
    
    def __init__(self, from_segm, to_segm, via_node, _type, parent_restriction):
        self.from_segm = from_segm
        self.to_segm   = to_segm
        self.via_node  = via_node
        self.angle    = None
        self._type    = _type
        self.parent_restriction   = parent_restriction
        
    def __str__(self):
        return ("from way "+str(self.from_segm.parent.get_id())+" (db id "+
                str(self.from_segm.get_db_id())+") to way " +
                str(self.to_segm.parent.get_id())+" (db id "+
                str(self.to_segm.get_db_id())+") via node"+str(self.via_node))
        
    def set_angle(self,angle):
        self.angle=angle
        
class RoutingWay(object):
    '''
    classdocs
    '''


    def __init__(self, osm_id):
        self._osm_id = osm_id
        
        self._nodes_placeholders = []
        self._segments_placeholders = []
        self._way_split=False
        
        self._oneway = False
        self._attributes = {}

        self._nodes = []
        self._split_nodes = []
        self._db_id = 0
        self.duration=-1
        self.f_speed = -1
        self.b_speed = -1
        self.max_speed = -1

        
    def get_node_ph_count(self):
        return len(self._nodes_placeholders)
        
    def get_id(self):
        return self._osm_id
    
    def get_db_id(self):
        return self._db_id

    def add_node_placeholder(self, node):
        if self._way_split:
            raise Exception("ERROR: Way already split, cannot add any more placehoders")
        self._nodes_placeholders.append(node)
        #node.use(self)

    def split_way_at_node_placeholders(self, id_generator, nodes, point_restrictions):
        if self._way_split:
            return
        
        self._way_split=True      
        nodez_len = len(self._nodes_placeholders)
        last_stop = 0
        segm_idx=0
                
        for idx in range(1, nodez_len):
            node_guid = self._nodes_placeholders[idx]
            if nodes.has_key(node_guid):
                new_segment = WaySegment(self,
                                         self._nodes_placeholders[last_stop:idx + 1],
                                         segm_idx,
                                         id_generator)
                self._segments_placeholders.append(new_segment)
                
                nodes[node_guid].use_segment(new_segment) 
                nodes[self._nodes_placeholders[last_stop]].use_segment(new_segment)
                if point_restrictions.has_key(node_guid):
                    point_restrictions[node_guid].add_source_segment(new_segment)
                
                last_stop = idx
                segm_idx+=1
                    
    def populate_node(self, node):
        populated_segments=[]
        if len(self._segments_placeholders) == 0:
            raise Exception("Way must be split before population any node")
        for segment in self._segments_placeholders:
            idx = segment.set_node(node)
            if idx is not None:
                populated_segments.append(idx)
        return populated_segments
            
    def get_segments(self):
        return self._segments_placeholders
       
    def get_attributes(self):
        return self._attributes
    
    def set_attributes(self, attribs, replace=False):
        for key,val in attribs.iteritems():
            if self._attributes.has_key(key):
                self._attributes[key]+=val
            else:
                self._attributes[key]=val
        
class WaySegment(object):
    '''
    classdocs
    '''

    def __init__(self, way, array, idx, db_id_generator):
        self._head = array[0]
        self._tail = array[-1]
        self._mids = [x for x in array[1:-1]]
        self.parent = way
        self.idx=idx
        self._db_id = next(db_id_generator)
        
    def get_segment_index(self):
        return self.idx
        
    def get_head(self):
        return self._head
    
    def get_tail(self):
        return self._tail
        
    def set_db_id(self, _id):
        self._db_id = _id
        
    def get_db_id(self):
        return self._db_id

    def get_wkt(self,nodes):
        return ("'LINESTRING(" + pair_as_string(nodes.get(self._head)) + "," + 
                   ','.join([pair_as_string(nodes.get(x)) for x in self._mids]) + 
                   ("," if len(self._mids)>0 else "" )+
                   pair_as_string(nodes.get(self._tail)) + ")'") 
        
    def get_node_id_near_end(self,end):
        if len(self._mids)>0:
            return self._mids[end]
        else:
            if end==0:
                return self.get_tail()
            else:
                return self.get_head()