# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import os
import collections
import copy
import json
from DefaultOrderedDict import DefaultOrderedDict
from subprocess import check_output
from collections import defaultdict
from datetime import date, datetime
from . import config
from . import markdown
from .messages import *
from .htmlhelpers import *
from .repository import *

class MetadataManager:
    @property
    def vshortname(self):
        if self.level is not None:
            return "{0}-{1}".format(self.shortname, self.level)
        return self.shortname

    @property
    def groupIsW3C(self):
        if self.group is None:
            return False
        return self.group.lower() in config.groupsInW3C

    def __init__(self, doc):
        self.doc = doc
        self.hasMetadata = False

        # required metadata
        self.abstract = []
        self.ED = None
        self.level = None
        self.shortname = None
        self.status = None

        # optional metadata
        self.advisementClass = "advisement"
        self.atRisk = []
        self.blockElements = []
        self.boilerplate = config.BoolSet(default=True)
        self.customTextMacros = []
        self.date = datetime.utcnow().date()
        self.deadline = None
        self.defaultBiblioStatus = "dated"
        self.editors = []
        self.group = None
        self.h1 = None
        self.ignoredTerms = []
        self.ignoredVars = []
        self.indent = 4
        self.inlineGithubIssues = False
        self.issueClass = "issue"
        self.issues = []
        self.issueTrackerTemplate = None
        self.linkDefaults = defaultdict(list)
        self.logo = ""
        self.mailingList = None
        self.mailingListArchives = None
        self.markupShorthands = config.BoolSet(["css", "dfn", "biblio", "markup", "idl", "algorithm"])
        self.noEditor = False
        self.noteClass = "note"
        self.opaqueElements = ["pre", "xmp", "script", "style"]
        self.previousEditors = []
        self.previousVersions = []
        self.repository = config.Nil()
        self.statusText = []
        self.testSuite = None
        self.title = None
        self.TR = None
        self.translateIDs = defaultdict(list)
        self.translations = []
        self.useDfnPanels = True
        self.prepTR = False
        self.useIAutolinks = False
        self.versionHistory = []
        self.warning = None
        self.workStatus = None

        self.otherMetadata = DefaultOrderedDict(list)

        self.manuallySetKeys = set()

    def addData(self, key, val):
        key = key.strip()
        if isinstance(val, basestring):
            val = val.strip()

        if key.startswith("!"):
            key = key[1:]
            self.otherMetadata[key].append(val)
            return

        if key not in ("ED", "TR", "URL"):
            key = key.title()

        if key not in knownKeys:
            die('Unknown metadata key "{0}". Prefix custom keys with "!".', key)
            return
        md = knownKeys[key]

        self.manuallySetKeys.add(key)

        val = md.parse(key, val)

        self.addParsedData(key, val)

    def addParsedData(self, key, val):
        md = knownKeys[key]
        result = md.join(getattr(self, md.attrName), val)
        setattr(self, md.attrName, result)


    def finish(self):
        # Do some "computed metadata", based on the value of other metadata.
        # Only call this when you're sure all metadata sources are parsed.
        if not self.repository:
            self.repository = getSpecRepository(self.doc)
        if self.repository.type == "github" and "feedback-header" in self.boilerplate and "repository-issue-tracking" in self.boilerplate:
            self.issues.append(("GitHub", self.repository.formatIssueUrl()))
        self.validate()

    def validate(self):
        if self.group == "byos":
            return True

        if not self.hasMetadata:
            die("The document requires at least one metadata block.")
            return

        # { MetadataManager attr : metadata name (for printing) }
        requiredSingularKeys = {
            'status': 'Status',
            'shortname': 'Shortname',
            'title': 'Title'
        }
        recommendedSingularKeys = {}
        requiredMultiKeys = {
            'abstract': 'Abstract'
        }

        if self.status not in config.noEDStatuses:
            requiredSingularKeys['ED'] = 'ED'
        if self.status in config.deadlineStatuses:
            requiredSingularKeys['deadline'] = 'Deadline'
        if self.status in config.TRStatuses:
            recommendedSingularKeys['date'] = 'Date'
        if self.status not in config.unlevelledStatuses:
            requiredSingularKeys['level'] = 'Level'
        if self.status not in config.shortToLongStatus:
            die("Unknown Status '{0}' used.", self.status)
        if not self.noEditor:
            requiredMultiKeys['editors'] = "Editor"
        if self.group and self.group.lower() == "csswg":
            requiredSingularKeys['workStatus'] = "Work Status"

        errors = []
        warnings = []
        for attr, name in requiredSingularKeys.items():
            if getattr(self, attr) is None:
                errors.append("    Missing a '{0}' entry.".format(name))
        for attr, name in recommendedSingularKeys.items():
            if getattr(self, attr) is None:
                warnings.append("    You probably want to provide a '{0}' entry.".format(name))
        for attr, name in requiredMultiKeys.items():
            if len(getattr(self, attr)) == 0:
                errors.append("    Must provide at least one '{0}' entry.".format(name))
        if warnings:
            warn("Some recommended metadata is missing:\n{0}", "\n".join(warnings))
        if errors:
            die("Not all required metadata was provided:\n{0}", "\n".join(errors))
            return

    def fillTextMacros(self, macros, doc=None):
        # Fills up a set of text macros based on metadata.
        if self.title:
            macros["title"] = self.title
            macros["spectitle"] = self.title
        if self.h1:
            macros["spectitle"] = self.h1
        macros["shortname"] = self.shortname
        if self.statusText:
            macros["statustext"] = "\n".join(markdown.parse(self.statusText, self.indent))
        else:
            macros["statustext"] = ""
        macros["level"] = str(self.level)
        macros["vshortname"] = self.vshortname
        if self.status == "FINDING" and self.group:
            macros["longstatus"] = "Finding of the {0}".format(self.group)
        elif self.status in config.shortToLongStatus:
            macros["longstatus"] = config.shortToLongStatus[self.status]
        else:
            macros["longstatus"] = ""
        if self.status in ("LCWD", "FPWD"):
            macros["status"] = "WD"
        else:
            macros["status"] = self.status
        if self.workStatus:
            macros["workstatus"] = self.workStatus
        if self.TR:
            macros["latest"] = self.TR
        if self.abstract:
            macros["abstract"] = "\n".join(markdown.parse(self.abstract, self.indent))
            macros["abstractattr"] = escapeAttr("  ".join(self.abstract).replace("<<","<").replace(">>",">"))
        macros["year"] = unicode(self.date.year)
        macros["date"] = unicode(self.date.strftime("{0} %B %Y".format(self.date.day)), encoding="utf-8")
        macros["cdate"] = unicode(self.date.strftime("%Y%m%d"), encoding="utf-8")
        macros["isodate"] = unicode(self.date.strftime("%Y-%m-%d"), encoding="utf-8")
        if self.deadline:
            macros["deadline"] = unicode(self.deadline.strftime("{0} %B %Y".format(self.deadline.day)), encoding="utf-8")
            macros["isodeadline"] = unicode(self.deadline.strftime("%Y-%m-%d"), encoding="utf-8")
        if self.status in config.TRStatuses:
            macros["version"] = "http://www.w3.org/TR/{year}/{status}-{vshortname}-{cdate}/".format(**macros)
        elif self.ED:
            macros["version"] = self.ED
        macros["annotations"] = config.testAnnotationURL
        if doc and self.vshortname in doc.testSuites:
            macros["testsuite"] = doc.testSuites[self.vshortname]['vshortname']
        if self.warning and len(self.warning) >= 2:
            macros["replacedby"] = self.warning[1]
        if self.warning and len(self.warning) >= 3:
            macros["snapshotid"] = self.warning[2]
        if self.warning and len(self.warning) >= 4:
            macros["snapshoturl"] = self.warning[3]
        macros["logo"] = self.logo
        if self.repository:
            macros["repository"] = self.repository.name
            macros["repositoryurl"] = self.repository.url
        if self.mailingList:
            macros["mailinglist"] = self.mailingList
        if self.mailingListArchives:
            macros["mailinglistarchives"] = self.mailingListArchives
        if self.status == "FPWD":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2016/W3C-WD"
        elif self.status == "FINDING":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2016/W3C-NOTE"
        else:
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2016/W3C-{0}".format(self.status)
        # Custom macros
        for name, text in self.customTextMacros:
            macros[name.lower()] = text

def parseDate(key, val):
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except:
        die("The {0} field must be in the format YYYY-MM-DD - got \"{1}\" instead.", key, val)
        return None

def parseLevel(key, val):
    return config.HierarchicalNumber(val)

def parseInteger(key, val):
    return int(val)

def parseBoolean(key, val):
    if val.lower() in ("true", "yes", "y", "on"):
        return True
    if val.lower() in ("false", "no", "n", "off"):
        return False
    die("The {0} field must be true/false, yes/no, y/n, or on/off. Got '{1}' instead.", key, val)
    return None

def parseWarning(key, val):
    if val.lower() == "obsolete":
        return "warning-obsolete",
    if val.lower() == "not ready":
        return "warning-not-ready",
    match = re.match(r"Commit +([^ ]+) +(.+) +replaced by +(.+)", val, re.I)
    if match:
        return "warning-commit", match.group(3), match.group(1), match.group(2)
    match = re.match(r"Branch +([^ ]+) +(.+) +replaced by +(.+)", val, re.I)
    if match:
        return "warning-branch", match.group(3), match.group(1), match.group(2)
    match = re.match(r"Replaced By +(.+)", val, re.I)
    if match:
        return "warning-replaced-by", match.group(1)
    match = re.match(r"New Version +(.+)", val, re.I)
    if match:
        return "warning-new-version", match.group(1)
    die('''Unknown value "{1}" for "{0}" metadata. Expected one of:
  obsolete
  not ready
  replaced by [new url]
  new version [new url]
  commit [snapshot id] [snapshot url] replaced by [master url]
  branch [branch name] [branch url] replaced by [master url]''', key, val)
    return None

def parseEditor(key, val):
    match = re.match(r"([^,]+) ,\s* ([^,]*) ,?\s* ([^,]*) ,?\s* ([^,]*)", val, re.X)
    pieces = [unescape(piece.strip()) for piece in val.split(',')]
    def looksLinkish(string):
        return re.match(r"\w+:", string) or looksEmailish(string)
    def looksEmailish(string):
        return re.match(r".+@.+\..+", string)
    data = {
        'name'   : pieces[0],
        'id'     : None,
        'org'    : None,
        'orglink': None,
        'link'   : None,
        'email'  : None
    }
    if len(pieces) == 4 and looksLinkish(pieces[2]) and looksLinkish(pieces[3]):
        data['org'] = pieces[1]
        if looksEmailish(pieces[2]):
            data['email'] = pieces[2]
            data['link'] = pieces[3]
        else:
            data['link'] = pieces[2]
            data['email'] = pieces[3]
    elif len(pieces) == 3 and looksLinkish(pieces[1]) and looksLinkish(pieces[2]):
        if looksEmailish(pieces[1]):
            data['email'] = pieces[1]
            data['link'] = pieces[2]
        else:
            data['link'] = pieces[1]
            data['email'] = pieces[2]
    elif len(pieces) == 3 and looksLinkish(pieces[2]):
        data['org'] = pieces[1]
        if looksEmailish(pieces[2]):
            data['email'] = pieces[2]
        else:
            data['link'] = pieces[2]
    elif len(pieces) == 2:
        # See if the piece looks like a link/email
        if looksLinkish(pieces[1]):
            if looksEmailish(pieces[1]):
                data['email'] = pieces[1]
            else:
                data['link'] = pieces[1]
        else:
            data['org'] = pieces[1]
    elif len(pieces) == 1:
        pass
    else:
        die("'{0}' format is '<name>, <company>?, <email-or-contact-page>?. Got:\n{1}", key, val)
        return []
    # Check if the org ends with a link
    if data['org'] is not None and " " in data['org'] and looksLinkish(data['org'].split()[-1]):
        pieces = data['org'].split()
        data['orglink'] = pieces[-1]
        data['org'] = ' '.join(pieces[:-1])
    # Check if the name ends with an ID.
    if data['name'] and re.search(r"\s\d+$", data['name']):
        pieces = data['name'].split()
        data['id'] = pieces[-1]
        data['name'] = ' '.join(pieces[:-1])
    return [data]


def parseCommaSeparated(key, val):
    return [term.strip().lower() for term in val.split(',')]

def parseLinkDefaults(key, val):
    defaultSpecs = defaultdict(list)
    for default in val.split(","):
        match = re.match(r"^([\w\d-]+)  (?:\s+\( ({0}) (?:\s+(TR|ED))? \) )  \s+(.*)$".format("|".join(config.dfnTypes.union(["dfn"]))), default.strip(), re.X)
        if match:
            spec = match.group(1)
            type = match.group(2)
            status = match.group(3)
            terms = match.group(4).split('/')
            dfnFor = None
            for term in terms:
                defaultSpecs[term.strip()].append((spec, type, status, dfnFor))
        else:
            die("'{0}' is a comma-separated list of '<spec> (<dfn-type>) <terms>'. Got:\n{1}", key, default)
            continue
    return defaultSpecs

def parseBoilerplate(key, val):
    boilerplate = config.BoolSet(default=True)
    for command in val.split(","):
        pieces = command.lower().strip().split()
        if len(pieces) != 2:
            die("Boilerplate metadata pieces are a boilerplate label and a boolean. Got:\n{0}", command)
            continue
        if pieces[0] == "omit":
            # legacy syntax; allows "omit foo" in addition to the normal "foo off"/etc
            boilerplate[pieces[1]] = False
        else:
            onoff = parseBoolean(pieces[1])
            if onoff is None:
                die("Boilerplate metadata pieces are a boilerplate label and a boolean. Got:\n{0}", command)
                continue
            boilerplate[pieces[0]] = onoff
    return boilerplate

def parseBiblioStatus(key, val):
    val = val.strip().lower()
    if val in ("current", "dated"):
        return val
    else:
        die("'{0}' must be either 'current' or 'dated'. Got '{1}'", key, val)
        return "dated"

def parseLinkedText(key, val):
    # Parses anything defined as "text url, text url, text url" into a list of 2-tuples.
    entries = []
    vals = [v.strip() for v in val.split(",")]
    for v in vals:
        entries.append(v.rsplit(" ", 1))
    return entries

def parseMarkupShorthands(key, val):
    # Format is comma-separated list of shorthand category followed by boolean.
    # Output is a dict of the shorthand categories with boolean values.
    vals = [v.strip() for v in val.lower().split(",")]
    ret = config.BoolSet(default=False)
    validCategories = frozenset(["css", "markup", "dfn", "biblio", "idl", "markdown", "algorithm"])
    for v in vals:
        pieces = v.split()
        if len(pieces) != 2:
            die("Markup Shorthand metadata pieces are a shorthand category and a boolean. Got:\n{0}", v)
            continue
        name, boolstring = pieces
        if name not in validCategories:
            die("Unknown Markup Shorthand category '{0}'.", name)
            continue
        onoff = parseBoolean(key, boolstring)
        if onoff is None:
            die("Markup Shorthand metadata pieces are a shorthand category and a boolean. Got:\n{0}", v)
            continue
        ret[name] = onoff
    return ret

def parseTextMacro(key, val):
    # Each Text Macro line is just a macro name (must be uppercase)
    # followed by the text it expands to.
    try:
        name, text = val.lstrip().split(None, 1)
    except:
        die("Text Macro lines must contain a macro name followed by the macro text. Got:\n{0}", val)
        return []
    if not re.match(r"[A-Z0-9-]+$", name):
        die("Text Macro names must be all-caps and alphanumeric. Got '{0}'", name)
        return []
    return [(name, text)]

def parseWorkStatus(key, val):
    # The Work Status is one of (completed, stable, testing, refining, revising, exploring, rewriting, abandoned).
    val = val.strip().lower()
    if val not in ('completed', 'stable', 'testing', 'refining', 'revising', 'exploring', 'rewriting', 'abandoned'):
        die("Work Status must be one of (completed, stable, testing, refining, revising, exploring, rewriting, abandoned). Got '{0}'. See http://fantasai.inkedblade.net/weblog/2011/inside-csswg/process for details.", val)
        return None
    return val

def parseRepository(key, val):
    # Shortname followed by url, or just url.
    # If just url, I'll try to recognize the shortname from it; otherwise it's the url again.
    val = val.strip()
    pieces = val.split(None, 1)
    if len(pieces) == 2:
        return Repository(url=pieces[0], name=pieces[1])
    elif len(pieces) == 1:
        # Try to recognize a GitHub url
        match = re.match("https://github.com/([\w-]+)/([\w-]+)/?$", val)
        if match:
            return GithubRepository(*match.groups())
        # If you just provide a user/repo pair, assume it's a github repo.
        # Will provide ways to opt into other repos when people care.
        match = re.match("([\w-]+)/([\w-]+)$", val)
        if match:
            return GithubRepository(*match.groups())
        # Otherwise just use the url as the shortname
        return Repository(url=val)
    else:
        die("Repository must be a url, optionally followed by a shortname. Got '{0}'", val)
        return config.Nil()

def parseTranslateIDs(key, val):
    translations = {}
    for v in val.split(","):
        pieces = v.strip().split()
        if len(pieces) != 2:
            die("‘Translate IDs’ values must be an old ID followed by a new ID. Got '{0}'", v)
            continue
        old,new = pieces
        translations[old] = new
    return translations

def parseTranslation(key, val):
    # Format is <lang-code> <url> [ [ , name <name-in-spec-lang> ] || [ , native-name <name-in-the-lang> ] ]?
    pieces = val.split(",")
    if not(1 <= len(pieces) <= 3):
        die("Format of a Translation line is <lang-code> <url> [ [ , name <name-in-spec-lang> ] || [ , native-name <name-in-the-lang> ] ]?. Got:\n{0}", val)
        return
    firstParts = pieces[0].split()
    if len(firstParts) != 2:
        die("First part of a Translation line must be a lang-code followed by a url. Got:\n{0}", pieces[0])
        return
    langCode, url = firstParts
    name = None
    nativeName = None
    for piece in pieces[1:]:
        k,v = piece.split(None, 1)
        if k.lower() == "name":
            name = v
        elif k.lower() == "native-name":
            nativeName = v
        else:
            die("Later parts of a Translation line must start with 'name' or 'native-name'. Got:\n{0}", piece)
    return [{"lang-code": langCode, "url": url, "name": name, "native-name": nativeName}]


def parse(lines, doc):
    # Given HTML document text, in the form of an array of text lines,
    # extracts all <pre class=metadata> lines and parses their contents.
    # Returns the text lines, with the metadata-related lines removed,
    # and a filled MetadataManager object

    newlines = []
    inMetadata = False
    lastKey = None
    blockSize = 0
    md = MetadataManager(doc)
    for line in lines:
        if not inMetadata and re.match(r"<pre .*class=.*metadata.*>", line):
            blockSize = 1
            inMetadata = True
            md.hasMetadata = True
            continue
        elif inMetadata and re.match(r"</pre>\s*", line):
            newlines.append("<!--line count correction {0}-->".format(blockSize+1))
            blockSize = 0
            inMetadata = False
            continue
        elif inMetadata:
            blockSize += 1
            if lastKey and (line.strip() == "" or re.match(r"\s+", line)):
                # empty lines, or lines that start with 1+ spaces, continue previous key
                md.addData(lastKey, line.lstrip())
            elif re.match(r"([^:]+):\s*(.*)", line):
                match = re.match(r"([^:]+):\s*(.*)", line)
                md.addData(match.group(1), match.group(2))
                lastKey = match.group(1)
            else:
                die("Incorrectly formatted metadata line:\n{0}", line)
                continue
        elif re.match(r"\s*<h1>.*?</h1>", line):
            title = re.match(r"\s*<h1>(.*?)</h1>", line).group(1)
            md.addData("Title", title)
        else:
            newlines.append(line)
    return newlines, md

def fromCommandLine(overrides, doc):
    # Given a list of strings representing command-line arguments,
    # finds the args that correspond to metadata keys
    # and fills a MetadataManager accordingly.
    md = MetadataManager(doc)
    for o in overrides:
        match = re.match("--md-([^ =]+)=(.+)", o)
        if not match:
            # Not a metadata key
            continue
        # Convert the key into a metadata name
        key = match.group(1).replace("-", " ")
        if key not in ("ED", "TR"):
            key = key.title()
        val = match.group(2).strip()
        md.addData(key, val)
    return md

def fromJson(data, doc):
    md = MetadataManager(doc)
    try:
        defaults = json.loads(data)
    except Exception, e:
        if data != "":
            die("Error loading default metadata:\n{0}", str(e))
        return md
    for key,val in defaults.items():
        md.addData(key, val)
    return md

def getSpecRepository(doc):
    '''
    Attempts to find the name of the repository the spec is a part of.
    Currently only searches for GitHub repos.
    Returns a "shortname" of the repo, and the full url.
    '''
    if doc and doc.inputSource and doc.inputSource != "-":
        source_dir = os.path.dirname(os.path.abspath(doc.inputSource))
        old_dir = os.getcwd()
        try:
            os.chdir(source_dir)
            with open(os.devnull, "wb") as fnull:
                remotes = check_output(["git", "remote", "-v"], stderr=fnull)
            os.chdir(old_dir)
            search = re.search(r"origin\tgit@github\.com:([\w-]+)/([\w-]+)\.git \(\w+\)", remotes)
            if search:
                return GithubRepository(*search.groups())
            search = re.search(r"origin\thttps://github.com/([\w-]+)/([\w-]+)\.git \(\w+\)", remotes)
            if search:
                return GithubRepository(*search.groups())
            return config.Nil()
        except:
            # check_output will throw CalledProcessError when not in a git repo
            os.chdir(old_dir)
            return config.Nil()

def parseDoc(doc):
    # Look through the doc for any additional metadata information that might be needed.

    for el in findAll(".replace-with-note-class", doc):
        removeClass(el, "replace-with-note-class")
        addClass(el, doc.md.noteClass)
    for el in findAll(".replace-with-issue-class", doc):
        removeClass(el, "replace-with-issue-class")
        addClass(el, doc.md.issueClass)
    for el in findAll(".replace-with-advisement-class", doc):
        removeClass(el, "replace-with-advisement-class")
        addClass(el, doc.md.advisementClass)

    if "feedback-header" in doc.md.boilerplate and "issues-index" in doc.md.boilerplate and find("." + doc.md.issueClass, doc) is not None:
            # There's at least one inline issue.
            doc.md.issues.append(("Inline In Spec", "#issues-index"))


def join(*sources):
    '''
    MetadataManager is a monoid
    '''
    md = MetadataManager(sources[0].doc)
    if any(x.hasMetadata for x in sources):
        md.hasMetadata = True
    for mdsource in sources:
        md.manuallySetKeys |= mdsource.manuallySetKeys
        for k in mdsource.manuallySetKeys:
            mdentry = knownKeys[k]
            md.addParsedData(k, getattr(mdsource, mdentry.attrName))
        for k,v in mdsource.otherMetadata.items():
            md.otherMetadata[k] = v
    return md

Metadata = collections.namedtuple('Metadata', ['humanName', 'attrName', 'join', 'parse'])

joinValue = lambda a,b: b
joinList = lambda a,b: a+b
def joinBoolSet(a,b):
    x = copy.deepcopy(a)
    x.update(b)
    return x
def joinDdList(a,b):
    x = defaultdict(list)
    x.update(a)
    x.update(b)
    return x
parseLiteral = lambda k,v: v
parseLiteralList = lambda k,v: [v]

knownKeys = {
    "Abstract": Metadata("Abstract", "abstract", joinList, parseLiteralList),
    "Advisement Class": Metadata("Advisement Class", "advisementClass", joinValue, parseLiteral),
    "At Risk": Metadata("At Risk", "atRisk", joinList, parseLiteralList),
    "Block Elements": Metadata("Block Elements", "blockElements", joinList, parseCommaSeparated),
    "Boilerplate": Metadata("Boilerplate", "boilerplate", joinBoolSet, parseBoilerplate),
    "Date": Metadata("Date", "date", joinValue, parseDate),
    "Deadline": Metadata("Deadline", "deadline", joinValue, parseDate),
    "Default Biblio Status": Metadata("Default Biblio Status", "defaultBiblioStatus", joinValue, parseBiblioStatus),
    "ED": Metadata("ED", "ED", joinValue, parseLiteral),
    "Editor": Metadata("Editor", "editors", joinList, parseEditor),
    "Former Editor": Metadata("Former Editor", "previousEditors", joinList, parseEditor),
    "Group": Metadata("Group", "group", joinValue, parseLiteral),
    "H1": Metadata("H1", "h1", joinValue, parseLiteral),
    "Ignored Terms": Metadata("Ignored Terms", "ignoredTerms", joinList, parseCommaSeparated),
    "Ignored Vars": Metadata("Ignored Vars", "ignoredVars", joinList, parseCommaSeparated),
    "Indent": Metadata("Indent", "indent", joinValue, parseInteger),
    "Inline Github Issues": Metadata("Inline Github Issues", "inlineGithubIssues", joinValue, parseBoolean),
    "Issue Class": Metadata("Issue Class", "issueClass", joinValue, parseLiteral),
    "Issue Tracker Template": Metadata("Issue Tracker Template", "issueTrackerTemplate", joinValue, parseLiteral),
    "Issue Tracking": Metadata("Issue Tracking", "issues", joinList, parseLinkedText),
    "Level": Metadata("Level", "level", joinValue, parseLevel),
    "Link Defaults": Metadata("Link Defaults", "linkDefaults", joinDdList, parseLinkDefaults),
    "Logo": Metadata("Logo", "logo", joinValue, parseLiteral),
    "Mailing List Archives": Metadata("Mailing List Archives", "mailingListArchives", joinValue, parseLiteral),
    "Mailing List": Metadata("Mailing List", "mailingList", joinValue, parseLiteral),
    "Markup Shorthands": Metadata("Markup Shorthands", "markupShorthands", joinBoolSet, parseMarkupShorthands),
    "No Editor": Metadata("No Editor", "noEditor", joinValue, parseBoolean),
    "Note Class": Metadata("Note Class", "noteClass", joinValue, parseLiteral),
    "Opaque Elements": Metadata("Opaque Elements", "opaqueElements", joinList, parseCommaSeparated),
    "Prepare For Tr": Metadata("Prepare For Tr", "prepTR", joinValue, parseBoolean),
    "Previous Version": Metadata("Previous Version", "previousVersions", joinList, parseLiteralList),
    "Repository": Metadata("Repository", "repository", joinValue, parseRepository),
    "Shortname": Metadata("Shortname", "shortname", joinValue, parseLiteral),
    "Status Text": Metadata("Status Text", "statusText", joinList, parseLiteralList),
    "Status": Metadata("Status", "status", joinValue, parseLiteral),
    "Test Suite": Metadata("Test Suite", "testSuite", joinValue, parseLiteral),
    "Text Macro": Metadata("Text Macro", "customTextMacros", joinList, parseTextMacro),
    "Title": Metadata("Title", "title", joinValue, parseLiteral),
    "TR": Metadata("TR", "TR", joinValue, parseLiteral),
    "Translate Ids": Metadata("Translate Ids", "translateIDs", joinDdList, parseTranslateIDs),
    "Translation": Metadata("Translation", "translations", joinList, parseTranslation),
    "URL": Metadata("URL", "ED", joinValue, parseLiteral), # URL is a synonym for ED
    "Use <I> Autolinks": Metadata("Use <I> Autolinks", "useIAutolinks", joinValue, parseBoolean),
    "Use Dfn Panels": Metadata("Use Dfn Panels", "useDfnPanels", joinValue, parseBoolean),
    "Version History": Metadata("Version History", "versionHistory", joinList, parseLiteralList),
    "Warning": Metadata("Warning", "warning", joinValue, parseWarning),
    "Work Status": Metadata("Work Status",  "workStatus", joinValue, parseWorkStatus)
}
