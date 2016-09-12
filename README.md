## About

pypgroutingloader is a Python package for loading an OpenStreetMap dump into a pgRouting-enabled database, preserving most routing restrictions present in the original dataset. Restrictions using via_way are currently ignored.

## Usage

```
pgroutingloader.py [-h] --file INPUT_FILE [--use-imposm]
                          [--connection-string GDAL_STRING] [--clean]
                          [--prefix-tables PREFIX] --length-projection EPSG_CODE
                          


Load OpenStreetMap dump into pgRouting database.

optional arguments:


  -h, --help            show this help message and exit
  --file INPUT_FILE, -f INPUT_FILE
                        OSM dump (either xml or pbf). Loading from pbf is
                        allowed only if imposm.parser is available on the
                        system
  --use-imposm, -b      Use the imposm.parser for parsing xml files
  --connection-string GDAL_STRING, -c GDAL_STRING
                        GDAL connection string for the database where the data
                        is to be loaded. If not present, will use info from
                        connection.cfg
  --clean, -d           Clear all data in the database before loading anything
                        from the dump
  --prefix-tables PREFIX, -p PREFIX
                        Prefix to use for loaded tables
  --length-projection EPSG_CODE, -e EPSG_CODE
                        EPSG of projection to use to compute way length

```
##Example run 
(using connection info from connection.cfg and EPSG:3844 for computing lenghts)

```
pgroutingloader.py -f E:\Data\romania-latest.osm.pbf -d -b -e 3844
