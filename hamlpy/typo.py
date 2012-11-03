# -*- coding: utf-8 -*-

import re
import codecs
import cStringIO

import html5lib

__all__ = ("typo", "typo_html", )

prepositions = map(unicode.strip, u"""
    и, да, а, но, или, что, чтобы, как, не, ни, ли, вот, вон,
    в, без, до, из, к, на, по, о, от, перед, при, через, с, у, за,
    над, об, под, про, для, вблизи, вглубь, вдоль, возле, около, вокруг,
    впереди, после, посредством, в роли, в зависимости от, путём, насчёт,
    по поводу, ввиду, по случаю, в течение, благодаря, несмотря на, спустя,
    из-под, из-за, несмотря на, в отличие от, в связи с
""".strip().split(","))

compound_prepositions = set(filter(lambda prep: " " in prep, prepositions))
simple_prepositions = set(filter(lambda prep: " " not in prep, prepositions))

dashes = map(unichr, range(0x2010, 0x2016))

html_substitutions = (
    ("&nbsp;", " "),
    ("&mdash;", "-"),
)

general_substitutions = (

    (r"\s+",
     " "),

    (r"(\w)\(",
     "\\1 ("),

    (r"\)(\w)",
     ") \\1"),

    (r"\(\s(\w)",
     "(\\1"),

    (r"(\w)\s\)",
     "\\1)"),

    (r"\s([\.\,\!\?\:\;])",
     "\\1"),

    (r"([\.\,\!\?\:\;])([^\s\.])",
     "\\1 \\2"),

    (r"(?<=[\d$])\s(?=\d)",
     "&nbsp;"),

    (r"\s-\s*",
     "&nbsp;&mdash; "),

     (ur"\s*-\s",
      "&nbsp;&mdash; "),

     (r"\.{3,}",
      "&hellip;"),

     (r"\.\.",
      "."),

)

sentence_start = re.compile(r"(?<=[\.\!\?]\s)\w", re.U)


def uppercase_group(match):
    return match.group().upper()


def typo(data, force_uppercase=False):
    if not isinstance(data, unicode):
        raise RuntimeError("`typo` requires unicode")
    data = data.strip()
    for entity, sub in html_substitutions:
        data = data.replace(entity, sub)
    for dash in dashes:
        data = data.replace(dash, "-")
    for pattern, sub in general_substitutions:
        regex = re.compile(pattern, re.U)
        data = regex.sub(sub, data)
    for compound_prep in compound_prepositions:
        replacement = compound_prep.replace(" ", "&nbsp;")
        regex = re.compile(ur"\b%s\b" % compound_prep, re.U)
        data = regex.sub(replacement, data)
        space_regex = re.compile(ur"\b%s\s" % re.escape(replacement), re.U)
        data = space_regex.sub("%s&nbsp;" % replacement, data)
    for simple_prep in simple_prepositions:
        regex = re.compile(ur"\b%s\s" % simple_prep, re.U)
        data = regex.sub("%s&nbsp;" % simple_prep, data)
    if force_uppercase:
        data = sentence_start.sub(uppercase_group, data)
    return data.strip()


def quoteattr(value):
    if '&' in value or '<' in value or '"' in value:
        value = value.replace('&', '&amp;').replace('<', '&lt;').replace('"', '&quot;')
    return u'"%s"' % value


def attr_str(attrs):
    if not attrs:
        return u''
    return u''.join([u' %s=%s' % (k, quoteattr(v)) for k, v in attrs.iteritems()])


class Tag(object):

    def __init__(self, out, tagname, attrs):
        self.out = out
        self.tagname = tagname
        self.out.write("<%s%s>" % (tagname, attr_str(attrs)))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        if exc_type:
            return
        self.out.write("</%s>" % self.tagname)


class TypoWalker(object):

    def __init__(self, fragment, force_uppercase, out):
        self.force_uppercase = force_uppercase
        self.out = codecs.getwriter('utf-8')(out)
        for child in fragment.childNodes:
            self.visit(child)

    def visit(self, node):
        if node.type is 5:
            with Tag(self.out, node.name, node.attributes):
                for child in node.childNodes:
                    self.visit(child)
        elif node.type is 4:
            if node.value.startswith(" "):
                self.out.write(" ")
            self.out.write(typo(node.value, self.force_uppercase))
        elif node.type is 6:
            pass
        else:
            raise RuntimeError("unknown node type %r" % node.type)


def typo_html(data, force_uppercase=False, out=None):
    if not isinstance(data, unicode):
        raise RuntimeError("`typo_html` requires unicod")
    return_value = False
    if not out:
        out = cStringIO.StringIO()
        return_value = True
    fragment = html5lib.parseFragment(data)
    TypoWalker(fragment, force_uppercase, out)
    if return_value:
        return out.getvalue()
