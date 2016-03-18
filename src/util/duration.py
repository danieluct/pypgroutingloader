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

SIMPLE_DURATION_MATCHER = re.compile("(?P<h>\d\d?:)?(?P<m>\d\d?:)?(?P<s>\d\d?)")
ISO8601_DURATION_MATCHER = re.compile("P(?P<y>\d+.?\d*Y)?(?P<mt>\d+.?\d*M)?(?P<d>\d+.?\d*D)?(T(?P<h>\d+.?\d*H)?(?P<m>\d+.?\d*M)?(?P<s>\d+.?\d*S)?)?")
TIME_UNIT_TO_SECONDS = {'y':3600 * 24 * 365, 'mt':3600 * 24 * 30, 
                        'd':3600 * 24, 'h':3600, 'm':60, 's':1}

def parse_duration(duration):
    actual_duration = -1
    
    if duration is None:
        return actual_duration
    match = SIMPLE_DURATION_MATCHER.match(duration)

    if match is not None:
        actual_duration = int(match.group('s'))
        if match.group('m') is None:
            actual_duration *= 60
            if match.group('h') is not None:
                actual_duration += 3600 * int(match.group('h')[:-1])
        else:
            actual_duration += 60 * int(match.group('m')[:-1])
            if match.group('h') is not None:
                actual_duration += 3600 * int(match.group('h')[:-1])
    else:
        match = ISO8601_DURATION_MATCHER.match(duration)
        if match is not None:
            actual_duration = 0
            for idx in TIME_UNIT_TO_SECONDS.keys():
                if match.group(idx) is not None:
                    actual_duration += TIME_UNIT_TO_SECONDS[idx] * float(match.group[:-1])
            
    return actual_duration
        
