import json
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from .mentor_colors import distinct_mentor_indexes, build_mentor_color_map, load_color_source, _lab


class MentorPresentationTests(SimpleTestCase):
    def test_python_and_frontend_share_the_same_graph_coloring_vectors(self):
        fixture = json.loads((Path(__file__).resolve().parent.parent / 'shared/mentor-color-fixtures.json').read_text(encoding='utf8'))
        graph = {}
        for names in fixture['groups']:
            for name in names:
                graph.setdefault(name, set()).update(set(names) - {name})
        self.assertEqual(distinct_mentor_indexes(graph), fixture['indexes'])
        reversed_graph = dict(reversed(list(graph.items())))
        self.assertEqual(distinct_mentor_indexes(reversed_graph), fixture['indexes'])
        entries = load_color_source()['distinctPalette']
        groups = [SimpleNamespace(students=SimpleNamespace(all=lambda names=names: [SimpleNamespace(mentor_name=n) for n in names]))
                  for names in fixture['groups']]
        self.assertEqual(build_mentor_color_map(groups), {name: entries[index]['dark'] for name, index in fixture['indexes'].items()})

    def test_screenshot_teacher_pair_is_not_given_similar_colors(self):
        graph = {'刘帅': {'刘杨', '张萌'}, '刘杨': {'刘帅', '张萌'}, '张萌': {'刘帅', '刘杨'}}
        indexes = distinct_mentor_indexes(graph)
        self.assertEqual(len(set(indexes.values())), 3)
        palette = load_color_source()['distinctPalette']
        a, b = (_lab(palette[indexes[name]]['light']) for name in ('刘帅', '张萌'))
        self.assertGreaterEqual(sum((x - y) ** 2 for x, y in zip(a, b)) ** .5, 20)
