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

def read_tags_from_osm_node(elem, guid, ignore_others=True):
    keyval = {}
    for kid in elem:
        if kid.tag == "tag":
            k = kid.get('k')
            if not keyval.has_key(k):
                keyval[k] = kid.get('v')
            else:
                print "multiple values for", k, "on node", guid
        elif not ignore_others:
            print elem.tag, kid.tag
    return keyval

def find_access_tag(source, access_tags_hierachy):
    for v in access_tags_hierachy:
        tag = source.get(v, None)
        if tag is not None and tag != '':
            return tag
    return ""

def is_not_empty(value):
    return value is not None and value != ""

def pair_as_string(pair):
    return ' '.join([str(x) for x in pair])
