# -*- coding: utf-8 -*-

import re
import codecs
import cStringIO

import html5lib
from colorama import Fore, Back

from django.conf import settings


__all__ = ("typo", "typo_html", )


def doublecase(*items):
    return list(items) + map(unicode.capitalize, items)


simple_prepositions = doublecase(
    u"и",
    u"да",
    u"а",
    u"но",
    u"или",
    u"что",
    u"чтобы",
    u"как",
    u"не",
    u"ни",
    u"ли",
    u"вот",
    u"вон",
    u"в",
    u"без",
    u"до",
    u"из",
    u"к",
    u"на",
    u"по",
    u"о",
    u"от",
    u"перед",
    u"при",
    u"через",
    u"с",
    u"у",
    u"за",
    u"над",
    u"об",
    u"под",
    u"для",
    u"из-под",
    u"из-за",
)


dashes = map(unichr, range(0x2010, 0x2016))


html_substitutions = (
    (u"&nbsp;", u" "),
    (u"&mdash;", u"-"),
)


general_substitutions = (

    # replace any whitespace symbols with simple whitespace
    (ur"\s{2,}", u" "),

    # add whitespace before and after parenthesis
    (ur"(?<=\w)\(", u" ("),
    (ur"\)(?=\w)", u") "),

    # remove whitespace inside parenthesis
    (ur"\(\s(?=\w)", u"("),
    (ur"(?<=\w)\s\)", u")"),

    # replace three or more dots with horizontal ellipsis
    (ur"\.{3,}", u"\u2026"),

    # replace two dots with one (two dots just dont make any sense)
    (ur"\.\.", u"."),

    # remove whitespace before punctuation symbols
    (ur"\s(?=\.|\,|\:|\;|\!|\?)", u""),

    # add whitespace after punctuation
    (ur"(?<=\,|\:|\;|\!|\?)(?=[а-яА-Я])", u" "), # only lowercase

    # add whitespace after dots
    (ur"(?<=\.)(?=[а-яА-Я])", u" "),

    # do not break dates
    (ur"(\d{4})\s?(гг?)(?:\.|\b)", u"\\1\u00a0\\2."),

    # do not break between digits or dollor sign
    (ur"(?<=[\d$])\s(?=\d)", u"\u00a0"),

    # if there is a whitespace before or after dash - make it mdash
    (ur"(?:\s-\s?|\s?-\s)", u"\u00a0\u2014 "),

    # do not break two short abbrs
    (ur"(\b\w{1,3})\.\s?(\w{1,3}\b)\.", u"\\1.\u00a0\\2."),

    # do not break short abbrs after digits
    (ur"(?<=\d)\s(?=\w{1,3}\.)", u"\u00a0"),

    # add some glue
    # (ur"(?<=\w)-(?=\w)", u"\u2060-\u2060"),

)


def sub_and_log_debug(regex, sub, data):

    def highlight_matches(match):
        return Back.MAGENTA + Fore.WHITE + match.group() + Back.RESET + Fore.RESET

    new_data = regex.sub(sub, data)
    if new_data != data:
        print "'%s%s%s' => %s%r%s" % (Fore.MAGENTA, regex.pattern, Fore.WHITE, Fore.CYAN, sub, Fore.RESET)
        print regex.sub(highlight_matches, data)
        print regex.sub(Fore.WHITE + Back.CYAN + sub + Fore.RESET + Back.RESET, data)
        print Back.RESET + Fore.RESET

    return new_data


if settings.DEBUG and getattr(settings, "LOG_TYPO", False):
    sub_and_log = sub_and_log_debug
else:
    sub_and_log = lambda regex, sub, data: regex.sub(sub, data)


def typo(data):
    if data and not isinstance(data, unicode):
        raise RuntimeError("`typo` requires unicode")

    # prepare input - remove html entities and replace
    # unicode dashes to default one
    data = data.strip()
    for entity, sub in html_substitutions:
        data = data.replace(entity, sub)
    data = sub_and_log(re.compile(ur"(?:%s)" % "|".join(dashes), re.U), "-", data)

    for pattern, sub in general_substitutions:
        regex = re.compile(pattern, re.U)
        data = sub_and_log(regex, sub, data)

    pattern = ur"\b(%s)\s" % "|".join(simple_prepositions)
    regex = re.compile(pattern, re.U)
    data = sub_and_log(regex, u"\\1\u00a0", data)

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

    def __init__(self, fragment, out):
        self.out = codecs.getwriter('utf-8')(out)
        for child in fragment.childNodes:
            self.visit(child)

    def visit(self, node):
        if node.type is 5:
            with Tag(self.out, node.name, node.attributes):
                for child in node.childNodes:
                    self.visit(child)
        elif node.type is 4:
            # add leading whitespace as is
            if node.value.startswith(" "):
                self.out.write(" ")
            self.out.write(typo(node.value))
        elif node.type is 6:
            # strip comments
            pass
        else:
            raise RuntimeError("unknown node type %r" % node.type)


def typo_html(data, out=None):
    if data and not isinstance(data, unicode):
        raise RuntimeError("`typo_html` requires unicode")
    return_value = False
    if not out:
        out = cStringIO.StringIO()
        return_value = True
    fragment = html5lib.parseFragment(data)
    TypoWalker(fragment, out)
    if return_value:
        return out.getvalue()
