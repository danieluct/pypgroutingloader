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

import argparse
import logging
import time
import warnings
import sys

import ConfigParser

from os.path import exists
from util.dbwriter import test_connection

IMPOSM_PRESENT = False

import xml.etree.cElementTree as ET
try:
    from imposm.parser import OSMParser
    IMPOSM_PRESENT = True
except ImportError:
    warnings.warn("imposm.parser library not found. Will use XML parser") 
    

from OSMEntities.Objects import RoutingRestriction, RoutingNode, RoutingWay, \
    ProperRestriction
import util.config as utils
from util import dbwriter
from util.config import SURE_AREA, BOTH_WAYS, ONEWAY_FORWARD, ONEWAY_BACKWARD,\
    load_connection_info_from_config, load_connection_info_from_gdal_string
from util.tag_utils import read_tags_from_osm_node
from util.synchronizedregistry import SynchronizedRegistry

from profile import way_function

'''
Created on Dec 14, 2015

@author: daniel.urda
'''

def db_id_generator():
    x = 1
    while True:
        yield x 
        x += 1

class NodeProcessor(object):
    def __init__(self, node_collection):
        self.nodes = SynchronizedRegistry()
        self.node_set = set(node_collection)
        logging.info("Nodes to read: %s"%(len(self.node_set),))
        
    def process_node_element(self, elem, use_imposm=False):
        guid = elem[0] if use_imposm else int(elem.get('id'))
        if guid in self.node_set:
            if use_imposm:
                payload = (elem[1], elem[2]) 
            else:
                payload = (float(elem.get('lon')),
                             float(elem.get('lat')))
            self.nodes.set(guid, payload)
        
    def process_nodes(self, nodez):
        for elem in nodez:
            self.process_node_element(elem, use_imposm=True)
            
    def get_node_coordinates(self):
        return self.nodes.get_backing_dict()

class NetworkProcessor(object):
    def __init__(self, const):
        self.const = const
        self.nodes = {}
        self.ways = SynchronizedRegistry()
        self.relation_restrictions = SynchronizedRegistry()
        self.barrier_restrictions = SynchronizedRegistry()
        self.normalized = False
        self.node_way_map = SynchronizedRegistry()
        
        
    def process_barrier_element(self, elem, use_imposm=False):
        guid = elem[0] if use_imposm else int(elem.get('id'))
        
        if use_imposm:
            res = True if elem[1].has_key('barrier') else None
        else:
            res = elem.find("tag[@k='barrier']")
             
        if res is not None:        
            keyval = elem[1] if use_imposm else read_tags_from_osm_node(elem, guid)
                        
            barrier_cost = self.const.get_barrier_cost(keyval)
            if barrier_cost is None:
                logging.warn("Unknown barrier value %s for node %s"%(keyval['barrier'],guid))
                del keyval
                return
            
            if barrier_cost == 0:
                del keyval
                return
            
            self.node_way_map.put(guid, None)            
            barrier = RoutingRestriction(guid, is_point=True)
            barrier.set_cost(barrier_cost)
            barrier.add_via_member("node", guid)            
            self.barrier_restrictions.set(guid, barrier)
            del keyval
            
    def process_relation_element(self, elem, use_imposm=False):
        guid = elem[0] if use_imposm else int(elem.get('id'))
    
        if use_imposm:
            process_relation = (elem[1].has_key('type') 
                               and self.const.is_valid_restriction(elem[1]['type']))
        else:
            res = elem.find("tag[@k='type']")
            process_relation = (self.const.is_valid_restriction(res.get('v')) 
                               if res is not None
                               else False)
                   
        if process_relation:
            temp_restriction = RoutingRestriction(guid)
            
            if use_imposm:
                members = elem[2]
                tags = elem[1]
            else:
                members = []
                for node in elem:
                    if node.tag == 'member':
                        members.append((int(node.get('ref')),
                                        node.get('type'),
                                        node.get('role')))
                tags = read_tags_from_osm_node(elem, guid)
            
            for member in members:
                node_ref, node_type, node_role = member
                if node_role in ('from', 'to'):
                    if node_type == 'way':
                        temp_restriction.add_end_member(node_role, node_ref)                   
                    elif node_type == 'node':
                        logging.warn("ERROR: Found node as end member in restriction %s"%(guid,))
                elif node_role == 'via':
                    if node_type == 'way':
                        temp_restriction.add_via_member(node_type, node_ref)
                    elif node_type == 'node':
                        self.node_way_map.put(node_ref, None)
                        temp_restriction.add_via_member(node_type, node_ref)
            for key, value in tags.iteritems():
                temp_restriction.add_property(key, value)                
                    
            if temp_restriction.seems_valid(): 
                if not self.const.is_excepted(tags):
                    actual_restriction = self.const.get_actual_restriction_type(tags)
                    if actual_restriction is None:
                        logging.warn("restriction not applicable %s"%(guid,))
                    elif (actual_restriction == 'no_u_turn' 
                          and len(temp_restriction.get_common_ends()) > 0):
                        logging.warn("no_u_turn restriction with common from and to %s"%(guid,))
                    else:
                        temp_restriction.get_properties()['restriction'] = actual_restriction
                        self.relation_restrictions.set(guid, temp_restriction)
                        return
                else:
                    logging.warn("excepted restriction %s; except tag was %s"%(guid, tags['except']))
            del temp_restriction
            del members
            del tags

    def process_way_element(self, elem, use_imposm=False):
        guid = elem[0] if use_imposm else int(elem.get('id'))
        
        if use_imposm:
            nodez = elem[2]
            tags = elem[1]
        else:
            nodez = []
            for kid in elem:
                if kid.tag == "nd":
                    node_id = int(kid.get('ref'))
                    nodez.append(node_id)
            tags = read_tags_from_osm_node(elem, guid)
                
        if (len(nodez) > 1 
            and self.const.is_routable_way(tags) 
            and self.const.is_area(tags) != SURE_AREA):
            
            if (self.const.is_routable_highway(tags) or
                self.const.is_adequate_ferry(tags) or
                self.const.is_routable_junction(tags)):
                    
                access = self.const.get_actual_access(tags)
                multiplier = self.const.get_access_cost_multiplier(access)
                if multiplier > 0:
                    tags['access'] = access
                    
                    first, last = -1, -1
                    useful_nodes = []
                    for node in nodez:
                        if first == -1:
                            first = node                                
                        if node != last:
                            last = node
                            useful_nodes.append(node)
                        else:
                            logging.warn("multiple successive appearances of node %s on way %s"%(node,guid))
 
                    if  len(useful_nodes) < 2:
                        logging.warn("way %s has only one distinct node"%(guid,))
                    else:
                        way = RoutingWay(guid)
                                               
                        try:
                            profile_result = way_function(tags)
                        except Exception:
                            logging.warn("ERROR: error profiling way %s"%(guid,))
                            way_function(tags, True)
                            profile_result = None
                        
                        # way.oneway = self.const.get_Direction(tags)
                        # way.max_speed = self.const.get_Speed_As_Number(tags)/ multiplier
                        if (profile_result is not None
                            and (profile_result.forward_speed > 0 or
                            profile_result.backward_speed > 0)):
                            if profile_result.forward_mode > 0:
                                if profile_result.backward_mode > 0:
                                    way.oneway = BOTH_WAYS
                                else:
                                    way.oneway = ONEWAY_FORWARD
                            elif profile_result.backward_mode > 0:
                                way.oneway = ONEWAY_BACKWARD
                            else:
                                logging.warn("unaccesible way %s"%(guid,))
                            
                            if profile_result.duration > 0:
                                way.duration = profile_result.duration                            
                            way.f_speed = profile_result.forward_speed
                            way.b_speed = profile_result.backward_speed
                            way.name = profile_result.name
                            way.set_attributes(self.const.get_useful_properties(tags))
                            
                            for node in useful_nodes:
                                way.add_node_placeholder(node)
                                self.node_way_map.put(node, guid)
                            self.node_way_map.put(first, guid)
                            self.node_way_map.put(last, guid)
                            
                            self.ways.set(guid, way)
                        else:
                            logging.warn("profile rejected way %s"%(guid,))
                            del way
                        
                elif access != 'no':
                    logging.warn("ignoring way %s because actual access is %s"%(guid,access))
        del nodez
        del tags
    
    def process_barriers(self, nodez):
        if self.normalized:
            raise Exception("ERROR: unable to process further elements after normalization")
        for elem in nodez:
            self.process_barrier_element(elem, use_imposm=True)
         
    def get_used_node_ids(self):
        return self.node_way_map.get_backing_dict().keys()
       
    def process_ways(self, wayz):
        if self.normalized:
            raise Exception("ERROR: unable to process further elements after normalization")
        for elem in wayz:
            self.process_way_element(elem, use_imposm=True)
                
    def process_relations(self, relationz):
        if self.normalized:
            raise Exception("ERROR: unable to process further elements after normalization")
        for elem in relationz:
            self.process_relation_element(elem, use_imposm=True)
            
    def normalize_network(self, edge_id_generator):
        if self.normalized:
            return
        self.normalized = True
        
        for key, val in self.node_way_map.get_backing_dict().iteritems():
            if len(val) > 1:
                self.nodes[key] = RoutingNode(key)
                
        self.ways = self.ways.get_backing_dict();
        self.barrier_restrictions = self.barrier_restrictions.get_backing_dict()
        self.relation_restrictions = self.relation_restrictions.get_backing_dict()
        
        for way in self.ways.values():
            way.split_way_at_node_placeholders(edge_id_generator, self.nodes,
                                           self.barrier_restrictions)
        restriction_keys = self.relation_restrictions.keys()
        
        for key in restriction_keys:
            restriction = self.relation_restrictions[key]
            actually_valid = restriction.validate_ways(self.ways)
            if not actually_valid:
                logging.warn("deleting restriction relation %s between unroutable ways"
                             %(key,))
                del self.relation_restrictions[key]
          
        restriction_keys = self.barrier_restrictions.keys()      
        for key in restriction_keys:
            restriction = self.barrier_restrictions[key]
            actually_valid = restriction.validate_ways(self.ways)
            if not actually_valid:
                logging.warn("deleting barrier restriction %s on unroutable way(s)"
                              %(key,))
                del self.barrier_restrictions[key]            


 
def run(target_db, file_path, length_projection,
        use_imposm=True, clean_db=True, table_prefix=''):    
    
    logging.info("parsing osm file "+file_path)
    
    const = utils.Configuration()    
    processor = NetworkProcessor(const)
    
    if use_imposm:
        parser = OSMParser(ways_callback=processor.process_ways,
                      nodes_callback=processor.process_barriers,
                      relations_callback=processor.process_relations)
        parser.parse(file_path)
        del parser
    else:
        proc_nodes, proc_ways, proc_rel = 0, 0, 0
        context = ET.iterparse(file_path)
        context = iter(context)
        event, root = context.next()     
        for event, elem in context:
            if elem.tag == "node":
                processor.process_barrier_element(elem)
                elem.clear()
                proc_nodes += 1
                if proc_nodes % 50000 == 0:
                    logging.debug("processed %s nodes" 
                                  % (proc_nodes,))    
            elif elem.tag == "way":
                processor.process_way_element(elem)
                elem.clear() 
                proc_ways += 1
                if proc_ways % 10000 == 0:
                    logging.debug("processed %s ways" 
                                  % (proc_ways,))                                   
            elif elem.tag == "relation":
                processor.process_relation_element(elem)
                elem.clear()
                proc_rel += 1
                if proc_rel % 1000 == 0:
                    logging.debug("processed %s relations" 
                                  % (proc_rel,))
            root.clear()
        del root, context
    logging.info("ways and restriction done read")
    
    edge_id_generator = db_id_generator()
    processor.normalize_network(edge_id_generator)
    logging.info("network normalized")
    
    node_processor = NodeProcessor(processor.get_used_node_ids())
    if use_imposm: 
        parser = OSMParser(coords_callback=node_processor.process_nodes)
        parser.parse(r"E:\Data\romania-latest.osm.pbf")
        del parser
    else:
        proc_nodes = 0
        context = ET.iterparse(file_path)
        context = iter(context)
        event, root = context.next()     
        for event, elem in context:
            if elem.tag == "node":
                node_processor.process_node_element(elem)
                elem.clear()
                proc_nodes += 1
                if proc_nodes % 50000 == 0:
                    logging.debug("processed %s nodes..." % (proc_nodes,))
            elif elem.tag in ('way', 'relation'):
                elem.clear()
            root.clear()
        del root, context
    logging.info("nodes done read")

    db_writer = dbwriter.DbWriter(target_db, table_prefix=table_prefix)

    db_writer.init_db(clean=clean_db)   
    for node in processor.nodes.values():
        db_writer.insert_node(node, node_processor.nodes.get(node.get_id()))
    db_writer.flush_caches()
    logging.info("nodes loaded")
    
    for way in processor.ways.values():
        for segment in way.get_segments():
            db_writer.insert_way(segment, node_processor.get_node_coordinates())
        db_writer.insert_way_properties(way)
    db_writer.flush_caches()
    logging.info("ways loaded")

    proper_restrictions_by_source = {}
    
    for key, val in processor.relation_restrictions.iteritems():
        restriction_map = val.get_as_proper_restrictions(node_processor.nodes)
        for node_key, restr_vals in restriction_map.iteritems():
            for restr_val in restr_vals:
                keypair = (restr_val.from_segm.get_db_id(), node_key)
                if not proper_restrictions_by_source.has_key(keypair):
                    proper_restrictions_by_source[keypair] = []
                proper_restrictions_by_source[keypair].append(restr_val)
    
    # simplified processing for point barriers            
    for key, val in processor.barrier_restrictions.iteritems():
        restriction_map = val.get_as_proper_restrictions(node_processor.nodes)
        for node_key, restr_vals in restriction_map.iteritems():
            for restr_val in restr_vals:
                keypair = (restr_val.from_segm.get_db_id(), node_key)
                if not proper_restrictions_by_source.has_key(keypair):
                    proper_restrictions_by_source[keypair] = []
                proper_restrictions_by_source[keypair].append(restr_val)
            
    for key, value in proper_restrictions_by_source.iteritems():
        node_id = key[1]
        only_restrictions = []
        for val in value:
            if val._type.startswith('only'):
                only_restrictions.append(val)
                
        only_route_segments = [val.to_segm.get_db_id() for val in only_restrictions]
                
            
        if len(only_route_segments) > 0:
            incident_segments = set([q.get_db_id() 
                                    for q in processor.nodes[node_id].get_edges()])
            block_routes = incident_segments.difference(only_route_segments)
            
            explicit_no = set()
            for val in value:
                if (val.to_segm.get_db_id() in block_routes 
                    or val._type.startswith('no')):
                    explicit_no.add(val.to_segm.get_db_id())
                    db_writer.insert_restriction(val)
                if  val._type == 'barrier':
                    logging.warn("barrier %s on only_* restriction",(val.via_node,))
            block_routes = block_routes.difference(explicit_no)
                    
            pivot = only_restrictions[0]
            for segm in processor.nodes[node_id].get_edges():
                if segm.get_db_id() in block_routes:
                    db_writer.insert_restriction(
                        ProperRestriction(pivot.from_segm, segm,
                                          None, None,
                                          pivot.parent_restriction))
            # print "------"
        else:
            has_explicit_no = False
            for val in value:
                if val._type.startswith('no'):
                    db_writer.insert_restriction(val)
                    has_explicit_no = True
            
            for val in value:
                if val._type == 'barrier':
                    if has_explicit_no:
                        logging.warn(" barrier %s on no_* restriction",(val.via_node,))
                    db_writer.insert_restriction(val)


    logging.info("restrictions loaded") 
   
    db_writer.rebuild_topology(epsg_projection=length_projection)
    logging.info("topology rebuilt")

    db_writer.close()
    logging.info("db written")
    

if __name__ == '__main__':
    config = ConfigParser.ConfigParser()
    config.read(['connection.cfg'])
    backup_connection_info = load_connection_info_from_config(config)
    logging.getLogger().setLevel(logging.INFO)
    
    parser = argparse.ArgumentParser(description=('Load OpenStreetMap dump '
                                                  +'into pgRouting database.'))
    parser.add_argument('--file', '-f', type=str, 
                        dest='input_file',
                        required=True,
                        help=('OSM dump (either xml or pbf). Loading from pbf '
                              +'is allowed only if imposm.parser is available '
                              +'on the system'))    
    parser.add_argument('--use-imposm', '-b', dest='use_imposm',
                        action='store_true',
                        help=('Use the imposm.parser for parsing xml files'))    
    parser.add_argument('--connection-string', '-c', type=str, 
                        dest='gdal_string', required=False,
                        help=('GDAL connection string for the database where '+
                              'the data is to be loaded. If not present, will '+
                              'use info from connection.cfg'))
    parser.add_argument('--clean', '-d', action='store_true',
                        dest='clean_db', 
                        help=('Clear all data in the database before '+
                              'loading anything from the dump'))
    parser.add_argument('--prefix-tables', '-p', type=str, 
                        dest='prefix', default='',required=False,
                        help=('Prefix to use for loaded tables'))
    parser.add_argument('--lenght-projection', '-e', type=str, 
                        dest='epsg_code', default='',required=True,
                        help=('EPSG of projection to use to compute way length'))
    args = parser.parse_args()
    
    if args.gdal_string is None:
        if backup_connection_info[1]:
            logging.error("GDAL connection string not present and configuration "
                          +"file is missing the following keywords:"
                          + ','.join(backup_connection_info[1]))
            sys.exit(1)
        else:
            connection_info = backup_connection_info[0]
    else:
        connection_info = load_connection_info_from_gdal_string(args.gdal_string)
        
    if connection_info is None:
        logging.error("Unable to read db connection info. Format should be: "
                      +"PG:\"dbname='databasename' host='addr' port='5432' "+
                      +"user='x' password='y'\"")
        sys.exit(1)
    
    error=test_connection(connection_info)
    if error is not None:
        logging.error("Unable to open connection to target db. Exception was: "+
                      error)
        sys.exit(1)

    if not exists(args.input_file):
        logging.error("Input file not found: "+args.input_file)
        sys.exit(1)
        
    if args.input_file.endswith('.pbf') and not IMPOSM_PRESENT:
        logging.error("Unable to parse pbf file as imposm.parser is not available")
        sys.exit(1)
        

    run(connection_info, args.input_file, 
        args.epsg_code,
        use_imposm=args.use_imposm, clean_db=args.clean_db, 
        table_prefix=args.prefix)
