import urllib.request
import urllib.parse
import json
import codecs
from threading import Timer

class DWCConnection:
  'Handles connection to DuetWebControl'

  default_timeout = 0.2
  reply_timeout = 30

  #Not supported dwc API: rr_delete, rr_fileinfo, rr_move, rr_mkdir
  def __rr_connect(self):
    reader = codecs.getreader('utf-8')
    response = json.load(reader(urllib.request.urlopen(self.__baseUrl+"rr_connect?password="+self.__passwd, timeout = self.default_timeout)))
    if response['err'] == 0 :
      self.connected = True
    return response['err']
  
  def __rr_disconnect(self):
    reader = codecs.getreader('utf-8')
    response = json.load(reader(urllib.request.urlopen(self.__baseUrl+"rr_disconnect", timeout = self.default_timeout)))
    if response['err'] == 0 :
      self.connected = False
    return response['err']

  def __rr_status(self, statusType):
    reader = codecs.getreader('utf-8')
    response = json.load(reader(urllib.request.urlopen(self.__baseUrl+"rr_status?type="+str(statusType), timeout = self.default_timeout)))
    if statusType == 1:
      self.status = response
    elif statusType == 2:
      self.extStatus = response
    elif statusType == 3:
      self.printStatus = response
  
  def __rr_gcode(self, code):
    reader = codecs.getreader('utf-8')
    response = json.load(reader(urllib.request.urlopen(self.__baseUrl+"rr_gcode?gcode="+urllib.parse.quote(code), timeout = self.default_timeout)))
    return response['buff']
  
  def __rr_download(self, name):
    return urllib.request.urlopen(self.__baseUrl+"rr_download?name="+urllib.parse.quote(name), timeout = self.default_timeout)

  def __rr_filelist(self, path, first=0):
    reader = codecs.getreader('utf-8')
    return json.load(reader(urllib.request.urlopen(self.__baseUrl+"rr_filelist?dir="+urllib.parse.quote(path)+"&first="+str(first), timeout = self.default_timeout)))

  def __rr_config(self):
    reader = codecs.getreader('utf-8')
    self.config = json.load(reader(urllib.request.urlopen(self.__baseUrl+"rr_config", timeout = self.default_timeout)))
  
  def __rr_reply(self):
    return urllib.request.urlopen(self.__baseUrl+"rr_reply", timeout = self.reply_timeout).read().decode("ascii")
  
  def __rr_fileinfo(self):
    reader = codecs.getreader('utf-8')
    self.fileInfo = json.load(reader(urllib.request.urlopen(self.__baseUrl+"rr_fileinfo", timeout = self.default_timeout)))
  
  def __statusUpdate(self):
    try:
      if self.__useExtStatus:
        self.__rr_status(2)
        self.status = self.extStatus
      else:
        self.__rr_status(1)
      if self.status['status'] in ['P', 'A', 'D', 'S', 'R', 'M']:
        self.__rr_status(3)
      self.__statusTimer = Timer(self.__updateInterval, self.__statusUpdate)
      self.__statusTimer.start()
    except:
      #assume timeout
      self.connected = False
      self.__statusTimer.cancel()
    
  def __init__(self, baseUrl, passwd = "", connect = True, useExtStatus = False, updateInterval=1000):
    self.__baseUrl = baseUrl
    self.__updateInterval = updateInterval/1000
    self.__passwd = passwd
    self.__useExtStatus = useExtStatus

    #init other variables
    self.__statusTimer = None
    self.status={}
    self.extStatus={}
    self.printStatus={}
    self.config={}
    self.fileInfo={}
    self.connected = False

    if ( connect ):
      self.connect()

  def __del__(self):
    if self.__statusTimer != None:
      self.__statusTimer.cancel()
      self.__statusTimer = None
  
  def connect(self):
    try:
      if self.__rr_connect() == 0:
        self.__rr_status(2)
        self.__rr_config()
        self.__statusUpdate()
        return 0
    except:
      return 2
  
  def changeUpdateInterval(self, updateInterval):
    self.__statusTimer.cancel()
    self.__updateInterval = updateInterval/1000
    self.__statusUpdate()
  
  def changeToEStatus(self, extStatus):
    self.__useExtStatus = extStatus
  
  def updateEStatus(self):
    if not self.connected:
      return
    self.__statusTimer.cancel()
    response = None
    try:
      response = self.__rr_status(2)
      self.__statusUpdate()
    except:
      #assume timeout
      self.connected = False
      self.__statusTimer.cancel()
    return response

  def disconnect(self):
    if not self.connected:
      return
    self.__statusTimer.cancel()
    self.__rr_disconnect()
    self.connected = False

  def runGCode(self, code, requestResponse = True):
    if not self.connected:
      return
    self.__statusTimer.cancel()
    response = ""
    try:
      self.__rr_gcode(code)
      if requestResponse:
        while response == "":
          response = self.__rr_reply()
      self.__statusUpdate()
    except:
      #assume timeout
      self.connected = False
      self.__statusTimer.cancel()
    return response
  
  def getFile(self, fileWithPath):
    if not self.connected:
      return
    self.__statusTimer.cancel()
    response = None
    try:
      response = self.__rr_download(fileWithPath)
      self.__statusUpdate()
    except:
      #assume timeout
      self.connected = False
      self.__statusTimer.cancel()
    return response
  
  def fileList(self, path):
    if not self.connected:
      return
    self.__statusTimer.cancel()
    response = []
    try:
      response = self.__rr_filelist(path, 0)
      nextresponse = response
      while nextresponse['next'] > 0:
        nextresponse = self.__rr_filelist(path, response['next'])
        response['files'].extend(nextresponse['files'])

      self.__statusUpdate()
    except:
      #assume timeout
      self.connected = False
      self.__statusTimer.cancel()
    return response
  
  def filamentList(self):
    return self.fileList('/filaments/')

  def updateFileInfo(self):
    try:
      self.__rr_fileinfo()
    except:
      #assume timeout
      self.connected = False
      self.__statusTimer.cancel()