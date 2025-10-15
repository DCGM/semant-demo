import unittest

from semant_demo.utils.template import Template, TemplateTransformer


class TestTemplate(unittest.TestCase):
    def test_render(self):
        template = Template("Hello {{ name }}!")
        rendered = template.render({"name": "World"})
        assert rendered == "Hello World!"


class TestTemplateTransformer(unittest.TestCase):
    def test_transform(self):
        transformer = TemplateTransformer()
        template = transformer("Hello {{ name }}!")
        rendered = template.render({"name": "World"})
        assert rendered == "Hello World!"
