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
import psycopg2.extensions
from psycopg2.extras import DictCursor
from util.geom import TextGeometry, wkt_point
import logging

psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)


class CachedWriter(object):
    def __init__(self, connection, statement, cache_entries=200):
        self.connection = connection
        self.statement = statement
        self.cache_entries = cache_entries
        self.rows = [] 
        psycopg2.extensions.register_adapter(TextGeometry,
                                             TextGeometry.adapter)
        
    def __call__(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        row_values = self.queue.get()
        
        while row_values is not None:
            self.rows.append(row_values)
            if len(self.rows) > self.cache_entries:
                entry_statement = self.statement.format(
                 ','.join(('(' + ','.join((unicode(x) for x in row)) + 
                           ')' for row in self.rows)))
                # print entry_statement
                cursor.execute(entry_statement)
                self.rows = []
            row_values = self.queue.get()
        
        if len(self.rows) > 0:
            entry_statement = self.statement.format(
             ','.join((u'(' + u','.join((unicode(x) for x in row)) + u')' for row in self.rows)))
            # print entry_statement
            cursor.execute(entry_statement)
            self.rows = []
        cursor.close()
        
    def _execute_insert(self):
        cursor = self.connection.cursor()
        records_list_template = ','.join(['%s'] * len(self.rows))
        insert_query = self.statement.format(records_list_template)        
        cursor.execute(insert_query, self.rows)
        cursor.close()
        
    def insert_row(self, row_values):
        self.rows.append(row_values)
        if len(self.rows) > self.cache_entries:
            self._execute_insert()
            self.rows = []
            
    def flush(self):
        if len(self.rows) > 0:
            self._execute_insert()
        self.rows = []

class DbWriter(object):
    '''
    classdocs
    '''


    def __init__(self, connection_properties, table_prefix=""):        

        self.table_prefix = table_prefix
        self.connection_properties = connection_properties
        self.connection_properties['cursor_factory'] = DictCursor
        self.connection = None
        self.nodes = None
        self.ways_cached_writer = None
        self.nodes_cached_writer = None
        self.restrictions_cached_writer = None
        self.properties_cached_writer = None

    def _get_connection(self):
        if self.connection is None:
            self.connection = psycopg2.connect(**self.connection_properties)
            self.connection.autocommit = True
        return self.connection      

    def _create_ways_table(self):
        connection = self._get_connection()
        cursor = connection.cursor()
        drop_statement = ('DROP TABLE IF EXISTS {0}ways CASCADE;').format(self.table_prefix)
        cursor.execute(drop_statement)
        create_statement = ('CREATE TABLE {0}ways ' + 
                            '(gid serial, source integer, target integer,' + 
                            ' x1 double precision, y1 double precision,' + 
                            ' x2 double precision, y2 double precision,' + 
                            ' from_osm_id bigint, to_osm_id bigint,' + 
                            ' maxspeed_forward double precision, maxspeed_backward double precision,' + 
                            ' osm_id bigint, segment_id integer, geom geometry(LineString,4326),' + 
                            ' oneway character varying(2), projected_length double precision,' + 
                            ' f_cost double precision, r_cost double precision,' + 
                            ' CONSTRAINT {0}ways_pkey PRIMARY KEY (gid))' + 
                            ' WITH (OIDS=FALSE);').format(self.table_prefix)
        
        cursor.execute(create_statement)
        cursor.execute('CREATE INDEX IF NOT EXISTS {0}ways_geom_idx ON {0}ways USING gist(geom);'.format(self.table_prefix))
        cursor.execute('CREATE INDEX IF NOT EXISTS {0}source_idx ON {0}ways USING btree(source);'.format(self.table_prefix))
        cursor.execute('CREATE INDEX IF NOT EXISTS {0}target_idx ON {0}ways USING btree(target);'.format(self.table_prefix))
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS {0}ways_gid_idx ON {0}ways USING btree(gid);'.format(self.table_prefix))
        cursor.execute("SELECT pgr_createTopology('{0}ways', 0.00001, 'geom', 'gid');".format(self.table_prefix))
        cursor.close()

    def _create_nodes_table(self):
        connection = self._get_connection()
        cursor = connection.cursor()
        drop_statement = ('DROP TABLE IF EXISTS {0}nodes CASCADE;').format(self.table_prefix)
        cursor.execute(drop_statement)
        create_statement = ('CREATE TABLE {0}nodes ' + 
                            '(gid serial NOT NULL,' + 
                            ' lon numeric(11,8),' + 
                            ' lat numeric(11,8),' + 
                            ' osm_id bigint,' + 
                            'CONSTRAINT {0}nodes_pkey PRIMARY KEY (gid))' + 
                            'WITH ( OIDS=FALSE);').format(self.table_prefix)
        
        cursor.execute(create_statement)
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS {0}nodes_gid_idx ON {0}nodes USING btree(gid);'.format(self.table_prefix))
        cursor.close()

    def _create_way_properties_table(self):
        connection = self._get_connection()
        cursor = connection.cursor()
        drop_statement = ('DROP TABLE IF EXISTS {0}way_properties CASCADE;').format(self.table_prefix)
        cursor.execute(drop_statement)
        create_statement = ('CREATE TABLE {0}way_properties ' + 
                            '(gid serial, way_id bigint, ' + 
                            ' key character varying, value character varying, ' + 
                            ' CONSTRAINT {0}way_properties_pkey PRIMARY KEY (gid))' + 
                            ' WITH (OIDS=FALSE);').format(self.table_prefix)
        
        cursor.execute(create_statement)
        cursor.execute('CREATE INDEX IF NOT EXISTS {0}way_fk_idx ON {0}way_properties USING btree(way_id);'.format(self.table_prefix)) 
        cursor.close()
        
    def _create_restrictions_table(self):
        connection = self._get_connection()
        cursor = connection.cursor()
        drop_statement = ('DROP TABLE IF EXISTS {0}restrictions CASCADE;').format(self.table_prefix)
        cursor.execute(drop_statement)
        create_statement = ('CREATE TABLE {0}restrictions ' + 
                            '(gid serial NOT NULL,' + 
                            ' from_way integer,' + 
                            ' to_way integer,' + 
                            ' via_ways character varying,'
                            ' osm_id bigint,' + 
                            ' cost numeric(8,2),' + 
                            ' via_node_id bigint,' + 
                            ' geom geometry(Point, 4326),' 
                            'CONSTRAINT {0}restrictions_pkey PRIMARY KEY (gid))' + 
                            'WITH ( OIDS=FALSE);').format(self.table_prefix)
        
        cursor.execute(create_statement)
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS {0}restrictions_gid_idx ON {0}restrictions USING btree(gid);'.format(self.table_prefix))  
        cursor.execute('CREATE INDEX IF NOT EXISTS {0}from_way_fk_idx ON {0}restrictions USING btree(from_way);'.format(self.table_prefix)) 
        cursor.execute('CREATE INDEX IF NOT EXISTS {0}to_way_fk_idx ON {0}restrictions USING btree(to_way);'.format(self.table_prefix))
        cursor.execute('CREATE INDEX IF NOT EXISTS {0}via_node_id_fk_idx ON {0}restrictions USING btree(via_node_id);'.format(self.table_prefix))
        cursor.execute('CREATE INDEX IF NOT EXISTS {0}restr_geom_idx ON {0}restrictions USING gist(geom);'.format(self.table_prefix))
        cursor.close()
        
    def init_db(self, clean=True):
        if clean:
            self._clean_db()
        self._init_pgrouting()
        self._create_ways_table()
        self._create_nodes_table()
        self._create_way_properties_table()
        self._create_restrictions_table()
        
    def rebuild_topology(self, epsg_projection='3844'):
        self.flush_caches()
        connection = self._get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT pgr_createTopology('{0}ways', 0.00001, 'geom', 'gid');".format(self.table_prefix))
        cursor.execute(("UPDATE {0}ways as w SET x1=n.lon, y1=n.lat " + 
                       "FROM {0}nodes as n WHERE w.from_osm_id=n.osm_id;").format(self.table_prefix))
        cursor.execute(("UPDATE {0}ways as w SET x2=n.lon, y2=n.lat " + 
                       "FROM {0}nodes as n WHERE w.to_osm_id=n.osm_id;").format(self.table_prefix))
        cursor.execute(("UPDATE {0}ways " + 
                       "SET projected_length=ST_Length(ST_Transform(geom,{1}));").format(self.table_prefix, epsg_projection))
        cursor.execute(("UPDATE {0}ways " + 
                       "SET f_cost=(CASE WHEN oneway='TF' THEN -1 ELSE (projected_length*3.6)/maxspeed_forward END), " + 
                       "r_cost=(CASE WHEN oneway='FT' THEN -1 ELSE (projected_length*3.6)/maxspeed_backward END)" + 
                       ";").format(self.table_prefix))
        cursor.close()
        
    def close(self):
        self.flush_caches()
        connection = self._get_connection()
        connection.close()
        
        
    def _init_pgrouting(self):
        connection = self._get_connection()
        cursor = connection.cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pgrouting;")
        cursor.close()
        
    def _clean_db(self):
        connection = self._get_connection()
        cursor = connection.cursor()
        cursor.execute("drop schema public cascade;")
        cursor.execute("create schema public;")
        cursor.close()
        
    def insert_way(self, segment, nodes):
        if self.ways_cached_writer is None:
            connection = self._get_connection()
            self.ways_cached_writer = CachedWriter(connection,
                          (u'INSERT INTO {0}ways ' + 
                           ' (gid, from_osm_id, to_osm_id, ' + 
                           '  maxspeed_forward, maxspeed_backward, oneway, osm_id, segment_id, geom) ' + 
                           ' VALUES {{0}};').format(self.table_prefix))
        # if segment.parent.max_speed<10:
        #   print segment.parent.get_id(),'computed speed',segment.parent.max_speed
        writable, geometry = segment.get_wkt(nodes)
        if writable:
            self.ways_cached_writer.insert_row(
                                             (segment.get_db_id(),
                                              segment.get_head(),
                                              segment.get_tail(),
                                              segment.parent.f_speed,
                                              segment.parent.b_speed,
                                              segment.parent.oneway,
                                              segment.parent.get_id(),
                                              segment.idx,
                                              TextGeometry(geometry)
                                              ))
        else:
            logging.error(("error writing segment %s of way %s: "+
                           "unable to find nodes %s") % (segment.idx, 
                                                         segment.parent.get_id(), 
                                                         geometry))
        
    def insert_node(self, node, geometry):
        if self.nodes_cached_writer is None:
            connection = self._get_connection()
            self.nodes_cached_writer = CachedWriter(connection,
                            (u'INSERT INTO {0}nodes ' + 
                           ' (lon, lat, osm_id) ' + 
                           ' VALUES {{0}};').format(self.table_prefix))
        self.nodes_cached_writer.insert_row((geometry[0], geometry[1], node.get_id()))
        
    def insert_restriction(self, proper_restriction, nodes):
        if self.restrictions_cached_writer is None:
            connection = self._get_connection()
            self.restrictions_cached_writer = CachedWriter(connection,
                            (u'INSERT INTO {0}restrictions ' + 
                           ' (from_way, to_way, via_ways, osm_id,' + 
                           ' cost, via_node_id, geom) '
                           ' VALUES {{0}};').format(self.table_prefix))
        self.restrictions_cached_writer.insert_row(
                                         (proper_restriction.from_segm.get_db_id(),
                                          proper_restriction.to_segm.get_db_id(),
                                          None,
                                          proper_restriction.parent_restriction._osm_id,
                                          proper_restriction.parent_restriction._cost,
                                          proper_restriction.via_node,
                                          TextGeometry(
                                             wkt_point(
                                                *nodes.get(proper_restriction.via_node)))
                                          )
                                                   )
            
    def insert_way_properties(self, way):
        if self.properties_cached_writer is None:
            connection = self._get_connection()
            self.properties_cached_writer = CachedWriter(connection,
                            (u'INSERT INTO {0}way_properties ' + 
                           ' (way_id, key, value) '
                           ' VALUES {{0}};').format(self.table_prefix))
                           
        for key, vals in way.get_attributes().iteritems():
            self.properties_cached_writer.insert_row((way.get_id(),
                                                       key,
                                                       vals))
            
    def flush_caches(self):
        if self.ways_cached_writer is not None:
            self.ways_cached_writer.flush()
        if self.nodes_cached_writer is not None:
            self.nodes_cached_writer.flush()
        if self.properties_cached_writer is not None:
            self.properties_cached_writer.flush()
        if self.restrictions_cached_writer is not None:
            self.restrictions_cached_writer.flush()
                             
    def set_node_dictionary(self, nodes):
        self.nodes = nodes

def test_connection(connection_properties):
    try:
        connection = psycopg2.connect(**connection_properties)
        connection.close()
    except Exception as e:
        return str(e)
    return None
