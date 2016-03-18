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
import pyproj

from math import atan2, pi

PROJ_WGS_84 = pyproj.Proj(init='EPSG:4326')
PROJ_MERCATOR = pyproj.Proj(init='EPSG:3857')

COORDINATE_PRECISION = 1000000.0
LON = 1
LAT = 0


def get_angle_between_points(point1, point2, point3): 

    m_point1 = pyproj.transform(PROJ_WGS_84, PROJ_MERCATOR, 
                                point1[LON], point1[LAT])
    m_point2 = pyproj.transform(PROJ_WGS_84, PROJ_MERCATOR, 
                                point2[LON], point2[LAT])
    m_point3 = pyproj.transform(PROJ_WGS_84, PROJ_MERCATOR, 
                                point3[LON], point3[LAT])
    
    v1x = (m_point1[LON] - m_point2[LON])  # / COORDINATE_PRECISION
    v1y = m_point1[LAT] - m_point2[LAT]
    v2x = (m_point3[LON] - m_point2[LON])  # / COORDINATE_PRECISION
    v2y = m_point3[LAT] - m_point2[LAT]
    
    angle = (atan2(v2y, v2x) - atan2(v1y, v1x)) * 180. / pi
    while angle < 0:
        angle += 360.
    return angle
