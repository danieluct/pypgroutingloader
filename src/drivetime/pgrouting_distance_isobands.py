'''
Copyright (c) 2016 daniel.urda

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Uses code from https://github.com/rveciana/geoexamples/blob/master/python/raster_isobands/isobands_matplotlib.py
'''

'''
isobands_matplotlib.py is a script for creating isobands.
Works in a similar way as gdal_contour, but creating polygons
instead of polylines

This version requires matplotlib, but there is another one
'''

import sys
import uuid
import time
import matplotlib.pyplot as plt

import psycopg2.extensions
from psycopg2.extras import DictCursor
from scipy.interpolate import griddata
from math import floor, ceil

from numpy import arange
from numpy import meshgrid
from osgeo import ogr
from osgeo.osr import SpatialReference

connString = 'PG:dbname=test_pyosm host=localhost user=postgres  password=*** port=5433'
connParams = {'database':"test_pyosm",
              'host':"localhost",
              'port':'5433',
              'user':"postgres",
              'password':"***"}

OGR_SQL = "select * from pgr_densedistance({0},{1},{2},'{3}')"
PG_SQL = "select cost, ST_X(geom) as x, ST_Y(geom) as y from pgr_densedistance(%s,%s,%s,%s)"

# "select cost, ST_AsLatLonText(geom,'D.DDDDD') as txt_geom from pgr_densedistance(%s,%s,%s,%s)"
class SpatialDataset:
    def __init__(self, params, zField='z'):
        ds = ogr.Open(connString)
        layer = ds.ExecuteSQL(OGR_SQL.format(*params))
        extent = layer.GetExtent()

        
        self.proj = layer.GetSpatialRef()
        self.geotransform = []        
        self.x = []
        self.y = []
        self.vals = []

        xMin, xMax, yMin, yMax = extent
        xSize, ySize = abs(xMax - xMin) / 0.0003, abs(yMin - yMax) / 0.0003
        self.size = xSize, ySize
        
        self.geotransform = [xMin, (xMax - xMin) / xSize, 0,
                             yMax, 0, (yMin - yMax) / ySize]

        
        feature = layer.GetNextFeature()        
        if feature.GetFieldIndex(zField) == -1:
            raise Exception('zField is not valid: ' + zField)
        while feature:  
            geometry = feature.GetGeometryRef()
            self.x.append(geometry.GetX())
            self.y.append(geometry.GetY()) 
            self.vals.append(feature.GetField(zField))  
            feature = layer.GetNextFeature()
        ds.Destroy()

class SpatialDataset2:
    def __init__(self, params, zField='z'):
        psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
        psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)        
        connection = psycopg2.connect(**connParams)

        self.geotransform = []        
        self.x = []
        self.y = []
        self.vals = []
        
        cursor = connection.cursor(cursor_factory=DictCursor)
        cursor.execute(PG_SQL, params)
        xMin, xMax, yMin, yMax = 91, -91, 181, -181
        for record in cursor:
            # print record['txt_geom']
            # lat, lon = [float(x) for x in record['txt_geom'].split(' ')]
            y = record['y']
            x = record['x']
            
            if yMin > y:
                yMin = y
            if yMax < y:
                yMax = y

            if xMin > x:
                xMin = x
            if xMax < x:
                xMax = x
                
            self.x.append(x)
            self.y.append(y)
            self.vals.append(record[zField])
        cursor.close()
        connection.close()
        # print xMin, xMax, yMin, yMax
        xSize, ySize = abs(xMax - xMin) / 0.0003, abs(yMin - yMax) / 0.0003
        self.size = xSize, ySize
        
        self.geotransform = [xMin, (xMax - xMin) / xSize, 0,
                             yMax, 0, (yMin - yMax) / ySize]
        
        self.proj = SpatialReference()
        self.proj.ImportFromEPSG(4326)
        xSize, ySize = abs(xMax - xMin) / 0.0003, abs(yMin - yMax) / 0.0003
        self.size = xSize, ySize
        
        self.geotransform = [xMin, (xMax - xMin) / xSize, 0,
                             yMax, 0, (yMin - yMax) / ySize]

def isobands(spatial_ds, offset, interval, min_level=None, max_level=None, nodata=300):
    '''
    The method that calculates the isobands
    '''
    xsize_in, ysize_in = spatial_ds.size
    geotransform_in = spatial_ds.geotransform
    srs = spatial_ds.proj
    # print geotransform_in

    # Creating the output vectorial file
    drv = ogr.GetDriverByName('Memory')
    
    # out_file = os.path.join(r"C:\tmp",str(uuid.uuid4())+".json")
    out_file = str(uuid.uuid4())
    # print out_file
    dst_ds = drv.CreateDataSource(out_file)
       
    dst_layer = dst_ds.CreateLayer('distances', geom_type=ogr.wkbPolygon,
        srs=srs)
    attr_name = 'cost'
    fdef = ogr.FieldDefn(attr_name, ogr.OFTReal)
    dst_layer.CreateField(fdef)


    x_pos = arange(geotransform_in[0],
        geotransform_in[0] + xsize_in * geotransform_in[1], geotransform_in[1])
    y_pos = arange(geotransform_in[3],
        geotransform_in[3] + ysize_in * geotransform_in[5], geotransform_in[5])
    x_grid, y_grid = meshgrid(x_pos, y_pos)
    linear_intp = griddata((spatial_ds.x, spatial_ds.y),
                           spatial_ds.vals,
                           (x_grid, y_grid),
                           method='linear',
                           fill_value=nodata)


    
    if min_level is None:
        min_value = min(spatial_ds.vals)
        min_level = offset + interval * floor((min_value - offset) / interval)

    if max_level is None:
        max_value = max(spatial_ds.vals)
        # Due to range issues, a level is added
        max_level = offset + interval * (1 + ceil((max_value - offset) / interval)) 

    levels = arange(min_level, max_level, interval)

    contours = plt.contourf(x_grid, y_grid, linear_intp, levels)
    # plt.show()

    first = True

    result = ('{"type": "FeatureCollection",' + 
           '"crs": { "type": "name", ' + 
           '"properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" } },' + 
           '"features": [')
                                                                            

    for level in range(len(contours.collections)):
        paths = contours.collections[level].get_paths()
        for path in paths:

            feat_out = ogr.Feature(dst_layer.GetLayerDefn())
            feat_out.SetField(attr_name, contours.levels[level])
            pol = ogr.Geometry(ogr.wkbPolygon)


            ring = None            
            
            for i in range(len(path.vertices)):
                point = path.vertices[i]
                if path.codes[i] == 1:
                    if ring != None:
                        pol.AddGeometry(ring)
                    ring = ogr.Geometry(ogr.wkbLinearRing)
                    
                ring.AddPoint_2D(point[0], point[1])
            

            pol.AddGeometry(ring)
            feat_out.SetGeometry(pol)

            if first:
                first = False
            else:
                result += ","
            result += feat_out.ExportToJson()

            # print pol.ExportToWkt()
            # print "-----"
            
            """
            if dst_layer.CreateFeature(feat_out) != 0:
                print "Failed to create feature in shapefile.\n"
                exit( 1 )
            """
            
            feat_out.Destroy()
    dst_ds.Destroy()
    # drv.DeleteDataSource( out_file )
    result += ']}'
    return result




def test():
    params = (44.42735, 26.09241, 300., '')
    print "Psycopg"
    start = time.time()    
    spatial_ds = SpatialDataset2(params, 'cost')
    isobands(spatial_ds, 0, 60, max_level=240)
    end = time.time()
    print "done", end - start
    """
    print "OGR"
    start = time.time()
    spatial_ds = SpatialDataset(params,'cost')
    isobands(spatial_ds, 0, 60)
    end = time.time()
    print "done", end-start
    """
    
if __name__ == "__main__":
    # print sys.argv
    blockage = ''
    if len(sys.argv) > 4 and len(sys.argv[4]) > 0:
        blockage = sys.argv[4]
    # print blockage
    params = (float(sys.argv[1]),
              float(sys.argv[2]),
              float(sys.argv[3]),
              blockage)
    spatial_ds = SpatialDataset2(params, 'cost')
    print isobands(spatial_ds, 0, 60, max_level=240),
