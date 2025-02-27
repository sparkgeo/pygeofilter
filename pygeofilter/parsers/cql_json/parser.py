# ------------------------------------------------------------------------------
#
# Project: pygeofilter <https://github.com/geopython/pygeofilter>
# Authors: Fabian Schindler <fabian.schindler@eox.at>
#
# ------------------------------------------------------------------------------
# Copyright (C) 2021 EOX IT Services GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies of this Software or works derived from this Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
# ------------------------------------------------------------------------------

from typing import Union
import json

from dateparser import parse as parse_datetime

from ...util import parse_duration
from ...values import Envelope, Geometry
from ... import ast

# https://portal.ogc.org/files/96288


COMPARISON_MAP = {
    'eq': ast.Equal,
    'lt': ast.LessThan,
    'lte': ast.LessEqual,
    'gt': ast.GreaterThan,
    'gte': ast.GreaterEqual,
}

SPATIAL_PREDICATES_MAP = {
    'intersects': ast.GeometryIntersects,
    'equals': ast.GeometryEquals,
    'disjoint': ast.GeometryDisjoint,
    'touches': ast.GeometryTouches,
    'within': ast.GeometryWithin,
    'overlaps': ast.GeometryOverlaps,
    'crosses': ast.GeometryCrosses,
    'contains': ast.GeometryContains,
}

TEMPORAL_PREDICATES_MAP = {
    'before': ast.TimeBefore,
    'after': ast.TimeAfter,
    'meets': ast.TimeMeets,
    'metby': ast.TimeMetBy,
    'toverlaps': ast.TimeOverlaps,
    'overlappedby': ast.TimeOverlappedBy,
    'begins': ast.TimeBegins,
    'begunby': ast.TimeBegunBy,
    'during': ast.TimeDuring,
    'tcontains': ast.TimeContains,
    'ends': ast.TimeEnds,
    'endedby': ast.TimeEndedBy,
    'tequals': ast.TimeEquals,
    # 'anyinteract': ast.TimeAnyInteract, # TODO?
}


ARRAY_PREDICATES_MAP = {
    'aequals': ast.ArrayEquals,
    'acontains': ast.ArrayContains,
    'acontainedBy': ast.ArrayContainedBy,
    'aoverlaps': ast.ArrayOverlaps,
}

ARITHMETIC_MAP = {
    '+': ast.Add,
    '-': ast.Sub,
    '*': ast.Mul,
    '/': ast.Div,
}


def walk_cql_json(node: dict, is_temporal: bool = False) -> ast.Node:
    if is_temporal and isinstance(node, str):
        # Open interval
        if node == '..':
            return None

        try:
            return parse_duration(node)
        except ValueError:
            value = parse_datetime(node)

        if value is None:
            raise ValueError(f'Failed to parse temporal value from {node}')

        return value

    if isinstance(node, (str, float, int, bool)):
        return node

    if isinstance(node, list):
        return [
            walk_cql_json(sub_node, is_temporal)
            for sub_node in node
        ]

    assert isinstance(node, dict)

    # check if we are dealing with a geometry
    if 'type' in node and 'coordinates' in node:
        # TODO: test if node is actually valid
        return Geometry(node)

    elif 'bbox' in node:
        return Envelope(*node['bbox'])

    # decode all other nodes
    for name, value in node.items():
        if name in ('and', 'or'):
            sub_items = walk_cql_json(value)
            last = sub_items[0]
            for sub_item in sub_items[1:]:
                last = (ast.And if name == 'and' else ast.Or)(
                    last,
                    sub_item,
                )
            return last

        elif name == 'not':
            # allow both arrays and objects, the standard is ambigous in
            # that regard
            if isinstance(value, list):
                value = value[0]
            return ast.Not(walk_cql_json(value))

        elif name in COMPARISON_MAP:
            return COMPARISON_MAP[name](
                walk_cql_json(value[0]),
                walk_cql_json(value[1]),
            )

        elif name == 'between':
            return ast.Between(
                walk_cql_json(value['value']),
                walk_cql_json(value['lower']),
                walk_cql_json(value['upper']),
                not_=False,
            )

        elif name == 'like':
            return ast.Like(
                walk_cql_json(value['like'][0]),
                value['like'][1],
                nocase=value.get('nocase', True),
                wildcard=value.get('wildcard', '%'),
                singlechar=value.get('singleChar', '.'),
                escapechar=value.get('escapeChar', '\\'),
                not_=False,
            )

        elif name == 'in':
            return ast.In(
                walk_cql_json(value['value']),
                walk_cql_json(value['list']),
                not_=False,
                # TODO nocase
            )

        elif name == 'isNull':
            return ast.IsNull(
                walk_cql_json(value),
                not_=False,
            )

        elif name in SPATIAL_PREDICATES_MAP:
            return SPATIAL_PREDICATES_MAP[name](
                walk_cql_json(value[0]),
                walk_cql_json(value[1]),
            )

        elif name in TEMPORAL_PREDICATES_MAP:
            return TEMPORAL_PREDICATES_MAP[name](
                walk_cql_json(value[0], is_temporal=True),
                walk_cql_json(value[1], is_temporal=True),
            )

        elif name in ARRAY_PREDICATES_MAP:
            return ARRAY_PREDICATES_MAP[name](
                walk_cql_json(value[0]),
                walk_cql_json(value[1]),
            )

        elif name in ARITHMETIC_MAP:
            return ARITHMETIC_MAP[name](
                walk_cql_json(value[0]),
                walk_cql_json(value[1]),
            )

        elif name == 'property':
            return ast.Attribute(value)

        elif name == 'function':
            return ast.Function(
                value['name'],
                walk_cql_json(value['arguments']),
            )


def parse(cql: Union[str, dict]) -> ast.Node:
    if isinstance(cql, str):
        cql = json.loads(cql)

    return walk_cql_json(cql)
