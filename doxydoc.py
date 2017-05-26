import sublime, sublime_plugin
import re
from datetime import date

def get_settings():
    return sublime.load_settings("DoxyDoc.sublime-settings")

def get_setting(key, default=None):
    return get_settings().get(key, default)

setting = get_setting

def get_template_args(templates):
    print('Before: {0}'.format(templates))
    # Strip decltype statements
    templates = re.sub(r"decltype\(.+\)", "", templates)
    # Strip default parameters
    templates = re.sub(r"\s*=\s*.+,", ",", templates)
    # Strip type from template
    templates = re.sub(r"[A-Za-z_][\w.<>]*\s+([A-Za-z_][\w.<>]*)", r"\1", templates)
    print('After: {0}'.format(templates))
    return re.split(r",\s*", templates)

def read_line(view, point):
    if (point >= view.size()):
        return

    next_line = view.line(point)
    return view.substr(next_line)

def get_function_args(fn_str):
    print('Before: {0}'.format(fn_str))
    # Remove references and pointers
    fn_str = fn_str.replace("&", "")
    fn_str = fn_str.replace("*", "")

    # Remove va_list and variadic templates
    fn_str = fn_str.replace("...", "")

    # Remove cv-qualifiers
    fn_str = re.sub(r"(?:const|volatile)\s*", "", fn_str)

    # Remove namespaces
    fn_str = re.sub(r"\w+::", "", fn_str)

    # Remove template arguments in types
    fn_str = re.sub(r"([a-zA-Z_]\w*)\s*<.+?>", r"\1", fn_str)

    # Remove parentheses
    fn_str = re.sub(r"\((.*?)\)", r"\1", fn_str)

    # Remove arrays
    fn_str = re.sub(r"\[.*?\]", "", fn_str)
    print('After: {0}'.format(fn_str))

    arg_regex = r"(?P<type>[a-zA-Z_]\w*)\s*(?P<name>[a-zA-Z_]\w*)"

    if ',' not in fn_str:
        if ' ' not in fn_str:
            return [("void", "")]
        else:
            m = re.search(arg_regex, fn_str)
            if m and m.group("type"):
                return [(m.group("type"), m.group("name"))]

    result = []
    for arg in fn_str.split(','):
        m = re.search(arg_regex, arg)
        if m and m.group('type'):
            result.append( (m.group('type'), m.group('name')) )

    return result

def partial_section_line(string):
    return section_line()[len(string):]

def section_line():
    return "/{}/".format("*"*(get_setting("section_line_length", 99)-2))

class DoxydocCommand(sublime_plugin.TextCommand):
    def set_up(self):
        identifier =  r"([a-zA-Z_]\w*)"
        function_identifiers = r"\s*(?:(?:inline|static|constexpr|friend|virtual|explicit|\[\[.+\]\])\s+)*"
        self.command_type = '@' if setting("javadoc", True) else '\\'
        self.regexp = {
            "templates": r"\s*template\s*<(.+)>\s*",
            "class": r"\s*(?:class|struct)\s*" + identifier + r"\s*{?",
            
            "function": function_identifiers + r"(?P<return>(?:typename\s*)?[\w:<>]+)?\s*"
                                               r"(?P<subname>[A-Za-z_]\w*::)?"
                                               r"(?P<name>operator\s*.{1,2}|[A-Za-z_:]\w*)\s*"
                                               r"\((?P<args>[:<>\[\]\(\),.*&\w\s=]*)\).+",

            "constructor": function_identifiers + r"(?P<return>)" # dummy so it doesn't error out
                                                  r"~?(?P<name>[a-zA-Z_]\w*)(?:\:\:[a-zA-Z_]\w*)?"
                                                  r"\((?P<args>[:<>\[\]\(\),.*&\w\s=]*)\).+"
        }

    def write(self, view, string):
        view.run_command("insert_snippet", {"contents": string })

    def run(self, edit, mode = None):
        if setting("enabled", True):
            self.set_up()
            snippet = self.retrieve_snippet(self.view)
            if snippet:
                self.write(self.view, snippet)
            else:
                sublime.status_message("DoxyDoc: Unable to retrieve snippet")

    def retrieve_snippet(self, view):
        point = view.sel()[0].begin()
        max_lines = setting("max_lines", 5)
        current_line = read_line(view, point)
        if not current_line or current_line.find("/**") == -1:
            # Strange bug..
            return "\n * ${0}\n */"

        # write a file header snippet if we are at the top
        if view.line(point).begin() == 0:
            return self.file_snippet(current_line)

        point += len(current_line) + 1

        next_line = read_line(view, point)

        if not next_line:
            return "\n * ${0}\n */"

        # if the next line is already a comment, no need to reparse
        if re.search(r"^\s*\*", next_line):
            return "\n * "

        retempl = re.search(self.regexp["templates"], next_line)

        if retempl:
            # The following line is either a template function or
            # templated class/struct
            template_args = get_template_args(retempl.group(1))
            point += len(next_line) + 1
            second_line = read_line(view, point)
            function_line = read_line(view, point)
            function_point = point + len(function_line) + 1

            for x in range(0, max_lines + 1):
                line = read_line(view, function_point)

                if not line:
                    break
                function_line += line
                function_point += len(line) + 1

            # Check if it's a templated constructor or destructor
            reconstr = re.match(self.regexp["constructor"], function_line)

            if reconstr:
                return self.template_function_snippet(reconstr, template_args)

            # Check if it's a templated function
            refun = re.match(self.regexp["function"], function_line)

            if refun:
                return self.template_function_snippet(refun, template_args)

            # Check if it's a templated class
            reclass = re.match(self.regexp["class"], second_line)

            if reclass:
                return self.template_snippet(template_args)

        function_lines = ''.join(next_line) # make a copy
        function_point = point + len(next_line) + 1

        for x in range(0, max_lines + 1):
            line = read_line(view, function_point)

            if not line:
                break

            function_lines += line
            function_point += len(line) + 1

        # Check if it's a regular constructor or destructor
        regex_constructor = re.match(self.regexp["constructor"], function_lines)
        if regex_constructor:
            return self.function_snippet(regex_constructor)

        # Check if it's a regular function
        regex_function = re.search(self.regexp["function"], function_lines)
        if regex_function:
            return self.function_snippet(regex_function)

        # Check if it's a regular class
        regex_class = re.search(self.regexp["class"], next_line)
        if regex_class:
            # Regular class
            return self.regular_snippet()

        # if all else fails, just send a closing snippet
        return "\n * ${0}\n */"

    def file_snippet(self, string):
        snippet = ( partial_section_line(string) + 
                  ("\n/**"
                   "\n * {0}author  ${{1:{author}}}"
                   "\n * {0}date    ${{2:{date}}}"
                   "\n * {0}version ${{3:1.0}}"
                   "\n * "
                   "\n * {0}copyright ${{4:{copyright}}}"
                   "\n * {0}brief     ${{5:[brief description]}}"
                   "\n * {0}details   ${{6:[long description]}}"
                   "\n * "
                   "\n */\n".format(self.command_type, author=get_setting("author", "author"), date=date.today(), copyright=get_setting("copyright", "copyright-text"))) +
                   section_line())
        return snippet

    def regular_snippet(self):
        snippet = ("\n * {0}brief ${{1:[brief description]}}"
                   "\n * {0}details ${{2:[long description]}}\n * \n */".format(self.command_type))
        return snippet

    def template_snippet(self, template_args):
        snippet = ("\n * {0}brief ${{1:[brief description]}}"
                   "\n * {0}details ${{2:[long description]}}\n * ".format(self.command_type))

        index = 3
        for x in template_args:
            snippet += "\n * {0}tparam {1} ${{{2}:[description]}}".format(self.command_type, x, index)
            index += 1

        snippet += "\n */"
        return snippet

    def template_function_snippet(self, regex_obj, template_args):
        snippet = ""
        index = 1
        snippet =  ("\n * {0}brief ${{{1}:[brief description]}}"
                    "\n * {0}details ${{{2}:[long description]}}\n * ".format(self.command_type, index, index + 1))
        index += 2

        # Function arguments
        args = regex_obj.group("args")

        if args and args.lower() != "void":
            args = get_function_args(args)
            for type, name in args:
                if type in template_args:
                    template_args.remove(type)
                snippet += "\n * {0}param {1} ${{{2}:[description]}}".format(self.command_type, name, index)
                index += 1

        for arg in template_args:
            snippet += "\n * {0}tparam {1} ${{{2}:[description]}}".format(self.command_type, arg, index)
            index += 1

        return_type = regex_obj.group("return")

        if return_type and return_type != "void":
            snippet += "\n * {0}return ${{{1}:[description]}}".format(self.command_type, index)

        snippet += "\n */"
        return snippet

    def function_snippet(self, regex_obj):
        fn = regex_obj.group(0)
        index = 1
        snippet =  ("\n * {0}brief ${{{1}:[brief description]}}"
                    "\n * {0}details ${{{2}:[long description]}}".format(self.command_type, index, index + 1))
        index += 2

        args = regex_obj.group("args")

        if args and args.lower() != "void":
            snippet += "\n * "
            args = get_function_args(args)
            for _, name in args:
                snippet += "\n * {0}param {1} ${{{2}:[description]}}".format(self.command_type, name, index)
                index += 1

        return_type = regex_obj.group("return")

        if return_type and return_type != "void":
            if index == 5:
                snippet += "\n * "
            snippet += "\n * {0}return ${{{1}:[description]}}".format(self.command_type, index)

        snippet += "\n */"
        return snippet

class DoxygenCompletions(sublime_plugin.EventListener):
    def __init__(self):
        self.command_type = '@' if setting('javadoc', True) else '\\'

    def default_completion_list(self):
        return [('addtogroup',      'addtogroup ${1:[group-name]} ${2:[group-title]}'),
                ('attention',       'attention ${1:[attention-text]}'),
                ('author',          'author ${1:[author]}'),
                ('authors',         'authors ${1:[author]}'),
                ('brief',           'brief ${1:[brief-text]}'),
                ('bug',             'bug ${1:[bug-text]}'),
                ('code',            'code \n* ${{1:[text]}}\n* {0}endcode'.format(self.command_type)),
                #('cond',            'cond ${{1:[section-name]}} \n* \n*/\n$2\n/// {0}endcond'.format(self.command_type)),
                ('copybrief',       'copybrief ${1:[link-object]}'),
                ('copydetails',     'copydetails ${1:[link-object]}'),
                ('copydoc',         'copydoc ${1:[link-object]}'),
                ('copyright',       'copyright ${1:[copyright-text]}'),
                ('date',            'date ${{1:{0}}}'.format(date.today())),
                ('defgroup',        'defgroup ${1:[group-name]} ${2:[group-title]}'),
                ('deprecated',      'deprecated ${1:[deprecated-text]}'),
                ('details',         'details ${1:[detailed-text]}'),
                ('dir',             'dir ${1:[path]}'),
                ('dontinclude',     'dontinclude ${1:[file-name]}'),
                ('dot',             'dot \n*   ${{1:[dot-graph]}}\n* {0}enddot'.format(self.command_type)),
                ('f[',              'f[\n*   ${{1:[formula]}}\n* {0}f]'.format(self.command_type)),
                ('example',         'example ${1:[file-name]}'),
                ('exception',       'exception ${1:[exception-object]} ${2:[description]}'),
                ('ifdox',           'if ${{1:[section-name]}} \n*   $2\n* {0}endif'.format(self.command_type)),
                ('ifnot',           'ifnot ${{1:[section-name]}} \n*   $2\n* {0}endif'.format(self.command_type)),
                ('image',           'image ${1:[format]} ${2:[file-name]}'),
                ('include',         'include ${1:[file-name]}'),
                ('includedoc',      'includedoc ${1:[file-name]}'),
                ('includelineno',   'includelineno ${1:[file-name]}'),
                ('ingroup',         'ingroup ${1:[group-name]...}'),
                ('internal',        'internal\n*   ${{1}}\n* {0}endinternal'.format(self.command_type)),
                ('invariant',       'invariant ${1:[invariant-text]}'),
                ('line',            'line ${1:[pattern]}'),
                ('mainpage',        'mainpage ${1:[title]}'),
                ('msc',             'msc \n*   ${{1:[msc-graph]}}\n* {0}endmsc'.format(self.command_type)),
                ('name',            'name ${1:[group-name]}'),
                ('note',            'note ${1:[note-text]}'),
                ('overload',        'overload ${1:[overload-object]}'),
                ('page',            'page ${1:[page-name]} ${2:[page-title]}'),
                ('par',             'par ${1:[paragraph-title]} ${2:[paragraph-text]}'),
                ('paragraph',       'paragraph ${1:[paragraph-name]} ${2:[paragraph-title]}'),
                ('param',           'param ${1:[parameter-name]} ${2:[description]}'),
                ('parblock',        'parblock\n*   ${{1:[paragraph-text]}}\n* {0}endparblock'.format(self.command_type)),
                ('post',            'post ${1:[postcondition-text]}'),
                ('pre',             'pre ${1:[precondition-text]}'),
                ('ref',             'ref ${1:[reference-name]}'),
                ('related',         'related ${1:[related-class]}'),
                ('relates',         'relates ${1:[related-class]}'),
                ('relatedalso',     'relatedalso ${1:[related-class]}'),
                ('relatesalso',     'relatesalso ${1:[related-class]}'),
                ('remark',          'remark ${1:[remark-text]}'),
                ('remarks',         'remarks ${1:[remark-text]}'),
                ('result',          'result ${1:[description]}'),
                ('return',          'return ${1:[description]}'),
                ('returns',         'returns ${1:[description]}'),
                ('retval',          'retval ${1:[return-value]} ${2:[description]}'),
                ('secreflist',      'secreflist\n*   {0}refitem ${{1:[reference-items]...}}\n* {0}endsecreflist'.format(self.command_type)),
                ('section',         'section ${1:[section-name]} ${2:[section-title]}'),
                ('see',             'see ${1:[referencing-text]}'),
                ('short',           'short ${1:[brief-text]}'),
                ('since',           'since ${1:[since-text]}'),
                ('skip',            'skip ${1:[pattern]}'),
                ('skipline',        'skipline ${1:[pattern]}'),
                ('snippet',         'snippet ${1:[file-name]} ${2:[block-id]}'),
                ('snippetdoc',      'snippetdoc ${1:[file-name]} ${2:[block-id]}'),
                ('snippetlineno',   'snippetlineno ${1:[file-name]} ${2:[block-id]}'),
                ('subpage',         'subpage ${1:[page-name]} ${2:[page-text]}'),
                ('subsection',      'subsection ${1:[subsection-name]} ${2:[subsection-title]}'),
                ('subsubsection',   'subsubsection ${1:[subsubsection-name]} ${2:[subsubsection-title]}'),
                ('test',            'test ${1:[test-description]}'),
                ('throw',           'throw ${1:[exception-object]} ${2:[description]}'),
                ('throws',          'throws ${1:[exception-object]} ${2:[description]}'),
                ('todo',            'todo ${1:[todo-text]}'),
                ('tparam',          'tparam ${1:[parameter-name]} ${2:[description]}'),
                ('until',           'until ${1:[pattern]}'),
                ('verbatim',        'verbatim\n* ${{1:[verbatim-text]}}\n* {0}endverbatim'.format(self.command_type)),
                ('version',         'version ${1:[version-text]}'),
                ('warning',         'warning ${1:[warning-message]}'),
                ('weakgroup',       'weakgroup ${1:[group-name]} ${2:[group-title]}')]

    def on_query_completions(self, view, prefix, locations):
        # Only trigger within comments
        if not view.match_selector(locations[0], 'comment'):
            return []

        pt = locations[0] - len(prefix) - 1
        # Get character before
        ch = view.substr(sublime.Region(pt, pt + 1))

        flags = sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS

        # Character given isn't \ or @
        if ch != self.command_type:
            return ([], flags)

        return (self.default_completion_list(), flags)
