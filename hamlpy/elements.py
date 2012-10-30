import re
import sys
from types import NoneType


class ObjectHack(object):
    
    def __init__(self, name):
        self._name = name
    
    def __getattr__(self, name):
        return ObjectHack("%s.%s" % (self._name, name))

    def __repr__(self):
        return "<ObjectHack %s>" % self._name

class LocalsHack(dict):

    def __getitem__(self, name):
        return ObjectHack(name)


class Element(object):
    """contains the pieces of an element and can populate itself from haml element text"""
    
    self_closing_tags = ('meta', 'img', 'link', 'br', 'hr', 'input', 'source', 'track')

    ELEMENT = '%'
    ID = '#'
    CLASS = '.'

    HAML_REGEX = re.compile(r"""
    (?P<tag>%\w+(\:\w+)?)?
    (?P<id>\#[\w-]*)?
    (?P<class>\.[\w\.-]*)*
    (?P<attributes>\{.*\})?
    (?P<nuke_outer_whitespace>\>)?
    (?P<nuke_inner_whitespace>\<)?
    (?P<selfclose>/)?
    (?P<django>=)?
    (?P<inline>[^\w\.#\{].*)?
    """, re.X|re.MULTILINE|re.DOTALL)

    _ATTRIBUTE_KEY_REGEX = r'(?P<key>[a-zA-Z_][a-zA-Z0-9_-]*)'
    #Single and double quote regexes from: http://stackoverflow.com/a/5453821/281469
    _SINGLE_QUOTE_STRING_LITERAL_REGEX = r"'([^'\\]*(?:\\.[^'\\]*)*)'"
    _DOUBLE_QUOTE_STRING_LITERAL_REGEX = r'"([^"\\]*(?:\\.[^"\\]*)*)"'
    _ATTRIBUTE_VALUE_REGEX = r'(?P<val>\d+|None(?![A-Za-z0-9_])|%s|%s)'%(_SINGLE_QUOTE_STRING_LITERAL_REGEX, _DOUBLE_QUOTE_STRING_LITERAL_REGEX)

    RUBY_HAML_REGEX = re.compile(r'(:|\")%s(\"|) =>'%(_ATTRIBUTE_KEY_REGEX))
    ATTRIBUTE_REGEX = re.compile(r'(?P<pre>\{\s*|,\s*)%s:\s*%s'%(_ATTRIBUTE_KEY_REGEX, _ATTRIBUTE_VALUE_REGEX))
    DJANGO_VARIABLE_REGEX = re.compile(r'^\s*=\s(?P<variable>[a-zA-Z_][a-zA-Z0-9._-]*)\s*$')


    def __init__(self, haml):
        self.haml = haml
        self.tag = None
        self.id = None
        self.classes = None
        self.attributes = ''
        self.self_close = False
        self.django_variable = False
        self.nuke_inner_whitespace = False
        self.nuke_outer_whitespace = False
        self.inline_content = ''
        self._parse_haml()
        
    def _parse_haml(self):
        split_tags = self.HAML_REGEX.search(self.haml).groupdict('')
        
        self.attributes_dict = self._parse_attribute_dictionary(split_tags.get('attributes'))
        self.tag = split_tags.get('tag').strip(self.ELEMENT) or 'div'
        self.id = self._parse_id(split_tags.get('id'))
        self.classes = ('%s %s' % (split_tags.get('class').lstrip(self.CLASS).replace('.', ' '), self._parse_class_from_attributes_dict())).strip()
        self.self_close = split_tags.get('selfclose') or self.tag in self.self_closing_tags
        self.nuke_inner_whitespace = split_tags.get('nuke_inner_whitespace') != ''
        self.nuke_outer_whitespace = split_tags.get('nuke_outer_whitespace') != ''
        self.django_variable = split_tags.get('django') != ''
        self.inline_content = split_tags.get('inline').strip()

    def _parse_class_from_attributes_dict(self):
        clazz = self.attributes_dict.get('class', '')
        if not isinstance(clazz, str):
            clazz = ''
            for one_class in self.attributes_dict.get('class'):
                clazz += ' '+one_class
        return clazz.strip()

    def _parse_id(self, id_haml):
        id_text = id_haml.strip(self.ID)
        if 'id' in self.attributes_dict:
            id_text += self._parse_id_dict(self.attributes_dict['id'])
        id_text = id_text.lstrip('_')
        return id_text
    
    def _parse_id_dict(self, id_dict):
        text = ''
        id_dict = self.attributes_dict.get('id')
        if isinstance(id_dict, str):
            text = '_'+id_dict
        else:
            text = ''
            for one_id in id_dict:
                text += '_'+one_id
        return text

    def _escape_attribute_quotes(self,v):
        '''
        Escapes quotes with a backslash, except those inside a Django tag
        '''
        escaped=[]
        inside_tag = False
        for i, _ in enumerate(v):
            if v[i:i+2] == '{%':
                inside_tag=True
            elif v[i:i+2] == '%}':
                inside_tag=False

            if v[i]=="'" and not inside_tag:
                escaped.append('\\')

            escaped.append(v[i])

        return ''.join(escaped)

    def _parse_attribute_dictionary(self, attribute_dict_string):
        attributes_dict = {}
        if (attribute_dict_string):
            attribute_dict_string = attribute_dict_string.replace('\n', ' ')
            try:

                # grab conditional attributes
                # conditional match is:
                #  attrname: if(condition)
                #  attrname: unless(condition)
                # means `attrname` will present only if `condition` evaluates to `True`
                # or `False` for unless case
                # useful for attributes like "checked", "required" etc
                conditional_matches = re.findall(r"[,\{]\s*([\w-]+)\:\s*(if|unless)\(\s*([\w=\s\.]+?)\s*\)", attribute_dict_string)
                # remove conditional matches from attribute string
                attribute_dict_string = re.sub(r"([,\{])\s*[\w-]+\:\s*(?:if|unless)\(\s*[\w=\s\.]+?\s*\)\s*,?", "\\1", attribute_dict_string)

                # grab conditional presence attributes
                # conditional presence is:
                #  attrname: if(condition, value)
                #  attrname: unless(condition, value)
                # means `attrname` will present and have `value` only if `condition` evaluates to `True`
                # of `False` for unless case
                # useful for adding "class" and "id"
                conditional_presence_matches = re.findall(r"[,\{]\s*([\w-]+)\:\s*(if|unless)\(\s*([\w=\s\.]+?)\s*,\s*(.+?)\s*\)", attribute_dict_string)
                # remove conditional presence matches from attribute string
                attribute_dict_string = re.sub(r"([,\{])\s*[\w-]+\:\s*(?:if|unless)\(\s*[\w=\s\.]+\s*,\s*.+?\s*\)\s*,?", "\\1", attribute_dict_string)

                # grab tag call attributes
                # tag call attribute is:
                #   attrname: tagname(arguments)
                # will render to attrname='{% tagname arguments %}'
                # useful for "href" attributes
                tag_call_matches = re.findall(r"[,\{]\s*([\w-]+)\:\s*(\w+)\(\s*(.+?)\s*\)\s*[\},]", attribute_dict_string)
                # remove tag call matches from attribute string
                attribute_dict_string = re.sub(r"([,\{])\s*[\w-]+\:\s*\w+\(\s*.+?\s*\)\s*,?", "\\1", attribute_dict_string)

                # converting all allowed attributes to python dictionary style

                # Replace Ruby-style HAML with Python style
                attribute_dict_string = re.sub(self.RUBY_HAML_REGEX, '"\g<key>":',attribute_dict_string)
                # Put double quotes around key
                attribute_dict_string = re.sub(self.ATTRIBUTE_REGEX, '\g<pre>"\g<key>":\g<val>', attribute_dict_string)
                # Parse string as dictionary

                # use hacked locals to allow literal django variables as values
                attributes_dict = eval(attribute_dict_string, LocalsHack())
                for k, v in attributes_dict.items():
                    if isinstance(k, ObjectHack):
                        k = k._name # we assume non-variable keys
                    if isinstance(v, ObjectHack):
                        v = '#{%s}' % v._name
                    attributes_dict[k] = v
                    if k != 'id' and k != 'class':
                        if isinstance(v, NoneType):
                            self.attributes += "%s " % (k,)
                        elif isinstance(v, int) or isinstance(v, float):
                            self.attributes += "%s='%s' " % (k, v)
                        else:
                            v = v.decode('utf-8')
                            self.attributes += "%s='%s' " % (k, self._escape_attribute_quotes(v))

                # append conditional attributes
                for attrname, check_type, condition in conditional_matches:
                    if check_type == "unless":
                        check_type = "if not"
                    self.attributes += "{%% %s %s %%} %s{%% endif %%}" % (check_type, condition, attrname)

                # append conditional presence attributes
                for attrname, check_type, condition, value in conditional_presence_matches:
                    if check_type == "unless":
                        check_type = "if not"
                    if re.compile(r"^'.+?'$", re.U).match(value) or re.compile(r'^".+?"$', re.U).match(value):
                        value = self._escape_attribute_quotes(value[1:-1])
                    else:
                        value = "#{%s}" % value # value is variable
                    if attrname == "class":
                        previous_value = attributes_dict.get("class")
                        if previous_value:
                            attributes_dict["class"] = "%s{%% %s %s %%} %s{%% endif %%}" % (previous_value, check_type, condition, value)
                        else:
                            attributes_dict["class"] = "{%% %s %s %%}%s{%% endif %%}" % (check_type, condition, value)
                    else:
                        if attributes_dict.get(attrname):
                            raise Exception('multiple values are allowed only for `class`')
                        if attrname == "id":
                            attributes_dict[attrname] = "{%% %s %s %%}%s{%% endif %%}" % (check_type, condition, value)
                        else:
                            if not self.attributes.endswith(" "):
                                self.attributes += " "
                            self.attributes += "{%% %s %s %%}%s='%s'{%% endif %%}" % (check_type, condition, attrname, value)

                # append tag call attributes
                for attrname, tagname, arguments in tag_call_matches:
                    value = "{%% %s %s %%}" % (tagname, arguments)
                    if attrname is "class":
                        previous_value = attributes_dict.get("class")
                        if previous_value:
                            attributes_dict["class"] = "%s %s" % (previous_value, value)
                        else:
                            attributes_dict["class"] = value
                    else:
                        if attributes_dict.get(attrname):
                            raise Exception('multiple values are allowed only for `class`')
                        if not self.attributes.endswith(" "):
                            self.attributes += " "
                        self.attributes += "%s='%s'" % (attrname, value)

                self.attributes = self.attributes.strip()
            except Exception, e:
                raise Exception('failed to decode: %s'%attribute_dict_string)

        return attributes_dict
