import sys
import traceback
import hashlib
import time
from random import random
from datetime import datetime

from javax.servlet.http import HttpServlet
from java.lang import System
from java.util import LinkedHashMap, ArrayList
from org.python.util import PythonInterpreter

from org.yaml.snakeyaml import Yaml
from java.io import FileWriter, FileInputStream, StringWriter

from pygments import highlight
from pygments.lexers import YamlLexer, PythonLexer, PythonTracebackLexer
from pygments.formatters import HtmlFormatter

# define a timeout wrapper for our rules
import threading
class TimeoutError(Exception): pass

def timeout(func, args=(), kwargs={}, timeout_duration=10, default=None):
    """This function will spawn a thread and run the given function
    using the args, kwargs and return the given default value if the
    timeout_duration is exceeded.
    """ 
    import threading
    class InterruptableThread(threading.Thread):
        def __init__(self):
            threading.Thread.__init__(self)
            self.result = default
        def run(self):
            self.result = func(*args, **kwargs)
    it = InterruptableThread()
    it.start()
    it.join(timeout_duration)
    if it.isAlive():
        raise TimeoutError()
    else:
        return it.result

# A monkey patch for using linkedhashmap iterators - thanks to Jim Baker
def monkeypatch_method_if_not_set(cls):
    def decorator(func):
        if not hasattr(cls, func.__name__):
            setattr(cls, func.__name__, func)
        return func
    return decorator

@monkeypatch_method_if_not_set(LinkedHashMap)
def iteritems(self):
    return ((entry.getKey(), entry.getValue()) for entry in self.entrySet())

@monkeypatch_method_if_not_set(ArrayList)
def append(self, item):
    self.add(item)

class NomjycContainer(): # A container object to shield the Servlet from
  pass                   # the code executed in the game.

class nomjyc (HttpServlet):
  """
This is the sandbox of the nomjyc web interface. Please refer to 
<a href="http://nomjyc.ath.cx:8080">nomjyc.ath.cx:8080</a> for the main game. 

Called without parameters, it will most probably just display the nomjyc rules,
read from the main nomjyc game. Send a GET or POST parameter called "test" to 
add an arbitrary rule to be executed at the end of the rule list.
"""

  def __init__(self):
    self.yaml          = Yaml()
    self.yamlLexer     = YamlLexer()
    self.pythonLexer   = PythonLexer()
    self.pythonTBLexer = PythonTracebackLexer()
    self.htmlFormatter = HtmlFormatter()

  def dumpData(self,c):
    rules = c.data["rules"]
    c.data["rules"] = "omitted"
    code = highlight(self.yaml.dump(c.data), self.yamlLexer, self.htmlFormatter)	
    c.data["rules"] = rules 
    return code

  def dumpYaml(self, anything):
    return highlight(self.yaml.dump(anything), self.yamlLexer, self.htmlFormatter)	
  def dumpPython(self, code):
    return highlight(code, self.pythonLexer, self.htmlFormatter)	
  def dumpPythonTB(self, code):
    return highlight(code, self.pythonTBLexer, self.htmlFormatter)	

  def explainException(self, title):
    nruter = "<div class=\"erroroutput\"><span class=\"gu\">%s</span>" % title
    exc_type, exc_value, exc_tb = sys.exc_info()
    for line in traceback.format_exception(exc_type, exc_value, exc_tb):
      nruter += "\n%s" % self.dumpPythonTB(line)
    return nruter + "</div>"
    
  def doGet(self, request, response):
    # Treat GET and POST equally
    self.doPost(request, response)

  DIV_HIDEOUS_BOX = "<div class=\"%s\"><div class=\"gh\">%s - <a href=\"javascript:ReverseDisplay('%s')\">show/hide %s</a></div><div id=\"%s\" style=\"display:%s\">%s</div>%s"
  def divHideCode(self, claz, title, id, data, visible=False, content="", openend=False):
    return self.DIV_HIDEOUS_BOX % (claz, title, id, content, id, visible and "show" or "none", data, openend and " " or "</div>")

  def doPost(self, request, response):
    c = NomjycContainer()
    c.parameters = request.getParameterMap()

    log = open("/var/log/nomjyc/sandbox.log","a")
    safelog = dict(c.parameters)
    if "pass" in safelog:
      safelog["pass"]=len(safelog["pass"])
    log.write(("[[%s]] %s %s\n" % (request.getRemoteAddr(), datetime.utcnow(), self.yaml.dump(safelog))).encode("utf-8"))
    log.close()

    output = "<div class=\"infobox\"><span class=\"gh\">nomjyc 0.1</span>\n"
    c.session    = {}
    if len(c.parameters)==0:
      output += "<pre>%s</pre>" % self.__doc__
    output += "</div>"

    c.salt="dckx"

    try:
      c.data = self.yaml.load(FileInputStream("/var/lib/tomcat6/webapps/nomjyc/data/nomjyc.yaml"))
    except:
      output += self.explainException("Error while initiating game state")

    # Print some debug information - for now.
    output += self.divHideCode("infobox", "Request", "reqi", self.dumpYaml(c.parameters), visible=True)
    output += self.divHideCode("infobox", "Data read", "dri", self.dumpYaml(c.data))

    # Add a final rule, if the test parameter is set
    if "test" in c.parameters:
      for code in c.parameters["test"]:
        c.data["rules"].add({"author":"impromptu", "code":code, "creation":datetime.utcnow(), "title":"test rule"})

    cycles = 1
    if "cycles" in c.parameters:
      try: 
        cycles = int(c.parameters["cycles"][0])
      except:
        pass
    if cycles<0 or cycles>3:
      cycles = 1

    # Execute all rules against the user input
    brain = PythonInterpreter()
    c.sandbox = True # a flag that gives away that we are in a sandbox
    for i in range(cycles):
      c.cycle = i    # a counter for the cycle we are in
      for rule in c.data["rules"][:]: # we are going to modify the rules. a lot. this prevents concurrent modification.
        try:
          output += self.divHideCode("rulebox", "Executing rule '%s'" % rule["title"], "id"+str(random()), self.dumpPython(rule["code"]), openend=True)
   	  err = StringWriter()
  	  out = StringWriter()
          checksum = hashlib.md5(self.yaml.dump(c.data)).hexdigest()
          brain.set("self", c)
          brain.setErr(err)
          brain.setOut(out)
          before = time.time()
          timeout (brain.exec,(rule["code"],),timeout_duration=30)
          runtime = int((time.time()-before) * 1000)
          changes = (checksum != hashlib.md5(self.yaml.dump(c.data)).hexdigest())
          output += "<div class=\"ruleoutput\">"
          if changes: output += "<div class=\"erroroutput\">This rule changed the game data.</div>"
          if (err.getBuffer().length()): output += "<div class=\"erroroutput\">Err:<br />%s</div>" % self.dumpPythonTB(err.toString().strip())
          if (out.getBuffer().length()): output += "<div class=\"gu\">Out:</div>"+out.toString().strip()
          output += "<div>(runtime: %sms)</div></div></div>" % runtime

        except Exception, ex:
          output += self.explainException("Execution failed") + "</div>"

    # Dump the data back to file - but not in the sandbox 
    #try:
    #  self.yaml.dump(c.data, FileWriter("/var/lib/tomcat6/webapps/sandbox/data/nomjyc.yaml"))    
    #except:
    #  output += self.explainException("Error while storing game state")

    # Print some debug information - for now.
    output += self.divHideCode("infobox", "Session data", "sess", self.dumpYaml(c.session), visible=True) 
    output += self.divHideCode("infobox", "Data stored", "dsf", self.dumpYaml(c.data)) 

    # Send all output to the user (xml or html?)
    toClient = response.getWriter()
    response.setContentType("text/html")
    toClient.println("""
<html>
  <head>
    <title>Nomjyc</title>
    <link rel="stylesheet" type="text/css" href="pygments.css" />
    <script type="text/javascript" src="nomjyc.js"></script>
  </head>
  <body>%s</body>
</html>
""" % output)
