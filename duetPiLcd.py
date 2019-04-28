#!/usr/bin/env python3
from dwcinterface import DWCConnection

from datetime import timedelta, datetime

from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior
from kivy.clock import Clock
from kivy.config import Config
from kivy.uix.filechooser import FileSystemAbstract, FileSystemLocal
from kivy.factory import Factory
from kivy.uix.screenmanager import NoTransition, SlideTransition

#TODO move these to config
URL = 'http://printerduet/'
PASSWD = ''

UPDATE_PRINT = 0.5
UPDATE_IDLE = 1
SCREEN_SAVER = 60 #only active on the print screen


DUETSTATUS = {
  'I': 'Idle',
  'P': 'Printing',
  'C': 'Configuring',
  'S': 'Paused',
  'D': 'Pausing',
  'R': 'Resuming',
  'B': 'Busy',
  'F': 'Updating',
  'H': 'Halted',
  'M': 'Simulating',
  'O': 'Off',
  'T': 'Changing Tool',
  'A': 'Paused',  #should be only in legacy status report, what we don't use. in that, S is halted
  #only used by this code:
  'CX': 'Connecting',
}

DUETPRINTS = ('Printing', 'Paused', 'Pausing', 'Resuming', 'Simulating')


class ImageButton(ButtonBehavior, Image):
  pass


class DuetMenuMainScreen(FloatLayout):
  lastStatus =  'Connecting' 

  def __updateElement(self, elementName, elementRoot, newText, formatString=''):
    if elementName in elementRoot.ids:
      prefixIndex = elementRoot.ids[elementName].text.rfind('\n')
      if prefixIndex >= 0:
        prefix = elementRoot.ids[elementName].text[:prefixIndex+1]
      else:
        prefix = ''
      if formatString == '':
        elementRoot.ids[elementName].text = prefix + str(newText)
      else:
        elementRoot.ids[elementName].text = prefix + formatString.format(newText)
  
  def __updateTimeElement(self, elementName, elementRoot, time, plusCurrent = False):
    if elementName in elementRoot.ids:
      if plusCurrent:
        res = datetime.now()
        res = res + timedelta(seconds=time)
        elementRoot.ids[elementName].text = '{:%H:%M:%S}'.format(res)
      else:
        time = int(time)
        days = 0
        while time > 86400:
          days = days + 1
          time = time - 86400
        if days > 0:
          elementRoot.ids[elementName].text = "{:d}d {:s}".format(days, str(timedelta(seconds=time)))
        else:
          elementRoot.ids[elementName].text = str(timedelta(seconds=time))
  
  def updateStatus(self, newStatus, extStatus, updateFileInfo):
    idleScreen = self.ids._screen_manager.get_screen('idleScreen')
    newStatus = DUETSTATUS.get(newStatus, 'Unknown:'+newStatus)
    ret = 0
    if self.lastStatus != newStatus:
      if newStatus == 'Connecting':
        #disconnect
        if 'buttons_bar' in idleScreen.ids:
          idleScreen.ids.buttons_bar.disabled = True
        if 'buttons_row' in idleScreen.ids:
          idleScreen.ids.buttons_row.disabled = True
      if self.lastStatus == 'Connecting':
        #connect
        if 'buttons_bar' in idleScreen.ids:
          idleScreen.ids.buttons_bar.disabled = False
        if 'buttons_row' in idleScreen.ids:
          idleScreen.ids.buttons_row.disabled = False
        if 'printerName' in idleScreen.ids:
          idleScreen.ids.printerName.text = extStatus['name']
      if ( newStatus in DUETPRINTS and self.lastStatus not in DUETPRINTS):  
        #print start
        ret = UPDATE_PRINT
        #change idle to print screen
        if self.ids._screen_manager.current == 'idleScreen':
          self.ids._screen_manager.transition = NoTransition()
          self.ids._screen_manager.current = 'printScreen'
          self.ids._screen_manager.transition = SlideTransition()
        #update return screens on screens used on print screen
        self.ids._screen_manager.get_screen('adjustScreen').returnScreen = 'printScreen'
        self.ids._screen_manager.get_screen('tempScreen').returnScreen = 'printScreen'
        self.ids._screen_manager.get_screen('macroScreen').returnScreen = 'printScreen'
        #update filename in print screens
        fileInfo = updateFileInfo()
        # print(fileInfo)
        self.__updateElement('fileName', self.ids._screen_manager.get_screen('printScreen'), fileInfo['fileName'])
      elif ( newStatus not in DUETPRINTS and self.lastStatus in DUETPRINTS):  
        ret = UPDATE_IDLE
        if self.ids._screen_manager.current in ('printScreen', 'printScreenSaver'):
          self.ids._screen_manager.transition = NoTransition()
          self.ids._screen_manager.current = 'idleScreen'
          self.ids._screen_manager.transition = SlideTransition()
        #update return screens on screens used on print screen
        self.ids._screen_manager.get_screen('adjustScreen').returnScreen = 'idleScreen'
        self.ids._screen_manager.get_screen('tempScreen').returnScreen = 'idleScreen'
        self.ids._screen_manager.get_screen('macroScreen').returnScreen = 'idleScreen'
      self.lastStatus = newStatus
      if 'statusBar' in idleScreen.ids:
        idleScreen.ids.statusBar.text = newStatus
    return ret
  
  #TODO this makes the screens and what can be on the screens pretty much hardocded
  #there should be a better solution to this, maybe saving the screens and their available elements in a config file
  #also, it would be nice to list the known ids somewhere
  def updateAdjustScreen(self, status, justOpened):
    currentScreen = self.ids._screen_manager.get_screen('adjustScreen')
    if justOpened:
      if self.lastStatus in DUETPRINTS and 'liveupdButton' in currentScreen.ids:
        currentScreen.ids.liveupdButton.state = 'down'
    self.__updateElement('babyStepValue', currentScreen, status['params']['babystep'], '{:4.2f}')
    self.__updateElement('speedFactorValue', currentScreen, status['params']['speedFactor'], '{:4.0f}')
    self.__updateElement('extrusionFactorValue', currentScreen, status['params']['extrFactors'][0], '{:4.0f}')
    if 'fanValue' in currentScreen.ids:
      currentScreen.ids.fanValue.value = status['params']['fanPercent'][0]

  def handleScreenSaver(self, state):
    if state == 'start':
      self.ssClock = Clock.schedule_once(self.handleScreenSaver, SCREEN_SAVER)
    elif state == 'restart':
      self.ssClock.cancel()
      self.ssClock = Clock.schedule_once(self.handleScreenSaver, SCREEN_SAVER)
    elif state == 'stop':
      self.ssClock.cancel()
    elif self.ids._screen_manager.current == 'printScreen': #triggered by clock on the right screen
      self.ids._screen_manager.transition = NoTransition()
      self.ids._screen_manager.current = 'printScreenSaver'
      self.ids._screen_manager.transition = SlideTransition()

  def updateScreen(self, status, printStatus, extStatus, updateExt, app):
    if self.ids._screen_manager.current == 'idleScreen' or self.ids._screen_manager.current == 'printScreen':
      currentScreen = self.ids._screen_manager.get_screen(self.ids._screen_manager.current)

      #set x/y/z - only supported geometry is cartesian
      # [] means not homed
      if extStatus['geometry'] == 'cartesian':
        if status['coords']['axesHomed'][0] == 1:
          formatString = '{:7.2f}'
        else:
          formatString = '[{:7.2f}]'
        self.__updateElement('xValue', currentScreen, status['coords']['xyz'][0], formatString)
    
        if status['coords']['axesHomed'][1] == 1:
          formatString = '{:7.2f}'
        else:
          formatString = '[{:7.2f}]'
        self.__updateElement('yValue', currentScreen, status['coords']['xyz'][1], formatString)

        if status['coords']['axesHomed'][2] == 1:
          formatString = '{:7.2f}'
        else:
          formatString = '[{:7.2f}]'
        self.__updateElement('zValue', currentScreen, status['coords']['xyz'][2], formatString)
        

      #set temps
      if status['temps']['bed']['state'] == 2:
        formatString = '{:7.1f}'
      else:
        formatString = '[{:7.1f}]'
      self.__updateElement('bedValue', currentScreen, status['temps']['bed']['current'], formatString)
      if status['temps']['bed']['state'] == 2:
        self.__updateElement('bedSetting', currentScreen, status['temps']['bed']['active'], '{:7.0f}')
      else:
        self.__updateElement('bedSetting', currentScreen, 'OFF')
      
      if status['temps']['state'][1] == 2:
        formatString = '{:7.1f}'
      else:
        formatString = '[{:7.1f}]'
      self.__updateElement('toolValue', currentScreen, status['temps']['current'][1], formatString)

      if status['temps']['state'][1] == 2:
        self.__updateElement('toolSetting', currentScreen, status['temps']['tools']['active'][0][0], '{:7.0f}')
      elif status['temps']['state'][1] == 1:
        self.__updateElement('toolSetting', currentScreen, status['temps']['tools']['standby'][0][0], '{:7.0f}')
      else:
          self.__updateElement('toolSetting', currentScreen, 'OFF')
    elif self.ids._screen_manager.current == 'moveXYScreen':
      if extStatus['geometry'] == 'cartesian':
        currentScreen = self.ids._screen_manager.get_screen('moveXYScreen')
        if status['coords']['axesHomed'][0] == 1:
          formatString = '{:7.2f}'
        else:
          formatString = '[{:7.2f}]'
        self.__updateElement('xValue', currentScreen, status['coords']['xyz'][0], formatString)
        if status['coords']['axesHomed'][1] == 1:
          formatString = '{:7.2f}'
        else:
          formatString = '[{:7.2f}]'
        self.__updateElement('yValue', currentScreen, status['coords']['xyz'][1], formatString)
    elif self.ids._screen_manager.current == 'moveZEScreen':
      if extStatus['geometry'] == 'cartesian':
        currentScreen = self.ids._screen_manager.get_screen('moveZEScreen')
        if status['coords']['axesHomed'][2] == 1:
          formatString = '{:7.2f}'
        else:
          formatString = '[{:7.2f}]'
        self.__updateElement('zValue', currentScreen, status['coords']['xyz'][2], formatString)
        self.__updateElement('eValue', currentScreen, status['coords']['xyz'][0], '{:.1f}')
    elif self.ids._screen_manager.current == 'tempScreen':
      currentScreen = self.ids._screen_manager.get_screen('tempScreen')
      self.__updateElement('bedValue', currentScreen, status['temps']['bed']['current'], '{:7.1f}')
      self.__updateElement('toolValue', currentScreen, status['temps']['current'][1], '{:7.1f}')

      if status['temps']['bed']['state'] == 2:
        self.__updateElement('bedSetting', currentScreen, status['temps']['bed']['active'], '{:3.0f}')
      else:
        self.__updateElement('bedSetting', currentScreen, '0')
      
      if status['temps']['state'][1] == 2:
        self.__updateElement('toolSetting', currentScreen, status['temps']['tools']['active'][0][0], '{:3.0f}')
      else:
        if status['temps']['state'][1] == 1:
          self.__updateElement('toolSetting', currentScreen, status['temps']['tools']['standby'][0][0], '{:3.0f}')
        else:
          self.__updateElement('toolSetting', currentScreen, '0')
      
      #filament stuff needs estatus to be up to date
      if 'tools' in status and 'loadUnloadButton' in currentScreen.ids and 'changeButton' in currentScreen.ids:
        filament = status['tools'][0]['filament']
        currentScreen.ids.loadUnloadButton.disabled = False
        self.__updateElement('currentFilament', currentScreen, filament)
        if filament == '':
          self.__updateElement('loadUnloadButton', currentScreen, 'Load')
          currentScreen.ids.changeButton.disabled = True
        else:
          self.__updateElement('loadUnloadButton', currentScreen, 'Unload')
          currentScreen.ids.changeButton.disabled = False
      else:
        currentScreen.ids.loadUnloadButton.disabled = True
        currentScreen.ids.changeButton.disabled = True
    elif self.ids._screen_manager.current == 'adjustScreen':
      currentScreen = self.ids._screen_manager.get_screen('adjustScreen')
      if 'liveupdButton' in currentScreen.ids and currentScreen.ids.liveupdButton.state == 'down':
        self.updateAdjustScreen(status, False)
    elif self.ids._screen_manager.current == 'printScreenSaver':
      currentScreen = self.ids._screen_manager.get_screen('printScreenSaver')
      if printStatus['timesLeft']['filament'] > 0:
        progress = 100 * printStatus['printDuration'] / (printStatus['printDuration'] + printStatus['timesLeft']['filament'])
      else:
        progress = printStatus['fractionPrinted'] #this is quite inaccurate, use the filament prediction instead if available
      self.__updateElement('printProgressText', currentScreen, progress, '{:4.0f}%')
      if 'printProgress' in currentScreen.ids:
        currentScreen.ids.printProgress.value = progress

      self.__updateTimeElement('printTime', currentScreen, printStatus['printDuration'])
      self.__updateTimeElement('timeLeft', currentScreen, printStatus['timesLeft']['filament'])
      self.__updateTimeElement('estimatedEnd', currentScreen, printStatus['timesLeft']['filament'], True)

    
    if self.ids._screen_manager.current == 'printScreen':
      #a bunch of stuff was already set on the main if as idlescreen
      currentScreen = self.ids._screen_manager.get_screen('printScreen')
      self.__updateElement('babyStepValue', currentScreen, status['params']['babystep'], '{:4.2f}')
      self.__updateElement('speedFactorValue', currentScreen, status['params']['speedFactor'], '{:4.0f}')
      self.__updateElement('extrusionFactorValue', currentScreen, status['params']['extrFactors'][0], '{:4.0f}')
      self.__updateElement('fanValueText', currentScreen, status['params']['fanPercent'][0], '{:4.1f}')
      self.__updateElement('speedRequesed', currentScreen, status['speeds']['requested'], '{:4.0f}')
      self.__updateElement('speedTop', currentScreen, status['speeds']['top'], '{:4.0f}')

      if printStatus['timesLeft']['filament'] > 0:
        progress = 100 * printStatus['printDuration'] / (printStatus['printDuration'] + printStatus['timesLeft']['filament'])
      else:
        progress = printStatus['fractionPrinted'] #this is quite inaccurate, use the filament prediction instead if available
      self.__updateElement('printProgressText', currentScreen, progress, '{:4.0f}%')
      if 'printProgress' in currentScreen.ids:
        currentScreen.ids.printProgress.value = progress

      self.__updateTimeElement('printTime', currentScreen, printStatus['printDuration'])
      self.__updateTimeElement('timeLeft', currentScreen, printStatus['timesLeft']['filament'])
      self.__updateTimeElement('estimatedEnd', currentScreen, printStatus['timesLeft']['filament'], True)

      if 'pauseResumeStopButton' in currentScreen.ids:
        if self.lastStatus not in ['Printing', 'Simulating'] and currentScreen.ids.pauseResumeStopButton.text == 'Pause':
          currentScreen.ids.pauseResumeStopButton.text = 'Resume\nStop'
        if self.lastStatus in ['Printing', 'Simulating'] and currentScreen.ids.pauseResumeStopButton.text == 'Resume\nStop':
          currentScreen.ids.pauseResumeStopButton.text = 'Pause'
      

class DuetFs(FileSystemAbstract):
  duetFiles = []
  duetFileArgs = []
  subpath = '/'

  def __init__(self, dwcConnection, path):
    self.dwcConnection = dwcConnection
    self.path = path

  def getsize(self, fn):
    filename = fn[fn.rfind('/')+1:]
    if filename in self.duetFiles:
      return self.duetFileArgs[ self.duetFiles.index(filename) ]['size']
    return 0
  
  def is_dir(self, fn):
    filename = fn[fn.rfind('/')+1:]
    if filename in self.duetFiles:
      if self.duetFileArgs[ self.duetFiles.index(filename) ]['type'] == 'd':
        return True
    return False
  
  def is_hidden(self, fn):
    return False
  
  #TODO directories won't behave well, the .. directory doesn't seem to work for some reason
  def listdir(self, fn):
    #print("ACCESS "+fn)
    resp = self.dwcConnection.fileList(self.path + fn)
    #print(resp)
    if 'files' in resp:
      self.subpath = fn
      self.duetFiles = []
      self.duetFileArgs = []
      for element in resp['files']:
        self.duetFiles.append(element['name'])
        args = dict()
        args['type'] = element['type']
        args['size'] = element['size']
        args['date'] = element['date'] #currently not used (unfortunately)
        self.duetFileArgs.append(args)    
    return self.duetFiles


class DuetMenuApp(App):
  def setFileSystem(self, fs, filescreen):
    filescreen.ids.files.file_system = fs
  
  def handleScreenSaver(self, state):
    self.gui.handleScreenSaver(state)

  def run_gcode(self, gcode, returnScreen, requestResponse = False, *largs):
    #print(gcode)
    resp = self.printerConnection.runGCode(gcode, requestResponse)
    self.gui.ids._screen_manager.transition.direction = 'down'
    if returnScreen != '':
      self.gui.ids._screen_manager.current = returnScreen

    if requestResponse:
      resp = resp.strip(' \t\n\r')
      if len(resp) > 0:
        responsePopup = Factory.DuetMessage()
        responsePopup.title = "Response"
        responsePopup.ids.popupLabel.text = resp
        responsePopup.open()
        Clock.schedule_once(responsePopup.dismiss, 2)
  
  #TODO this needs some work
  def run_gcode_ask(self, args):
    popup = Factory.DuetDecide()
    popup.title = args[0]
    popup.ids.popupLabel.text = args[1]
    popup.ids.okButton.bind(on_release=lambda x: self.run_gcode(popup.ids.popupLabel.text, 'idleScreen'))
    popup.open()
  
  def run_file(self, origin, file):
    if origin.startswith('gcode'):
      popup = Factory.DuetDecide()
      popup.title = "Start print?"
      popup.ids.popupLabel.text = file
      popup.ids.okButton.bind(on_release=lambda x:self.run_gcode("M32 "+file, 'idleScreen'))
      popup.open()
    elif origin.startswith('macro'):
      self.run_gcode('M98 P"0:/macros/' + file + '"', 'idleScreen', True) #name and path in quotes

  def filament(self, calledFrom, current):
    if calledFrom == 'Unload':
      self.run_gcode('M702', '', True)
    
    if calledFrom == 'Load' or calledFrom == 'Change':
      filamentsDet = self.printerConnection.filamentList()
      filaments = set()
      for filament in filamentsDet['files']:
        filaments.add(filament['name'])
      
      popup = Factory.DuetSelect()
      popup.title = "Select filament"
      popup.ids.popupSpinner.values = filaments
      popup.ids.popupSpinner.text = current
      if calledFrom == 'Load':
        popup.ids.okButton.bind(on_release=lambda x: self.run_gcode('M701 S"'+popup.ids.popupSpinner.text+'"\nM703', '', True))
      else:
        popup.ids.okButton.bind(on_release=lambda x: self.run_gcode('M702\nM701 S"'+popup.ids.popupSpinner.text+'"\nM703', '', True))
      popup.open()

  def adjust(self, really, what, value):
    if really:
      if what == 'babystep':
        self.run_gcode("M290 R0 S"+value.strip(), '', False)
      elif what == 'extrf':
        self.run_gcode("M221 S"+value.strip(), '', False)
      elif what == 'speedf':
        self.run_gcode("M220 S"+value.strip(), '', False)
      elif what == 'fan':
        self.run_gcode("M106 S"+'{:.2f}'.format(int(value)/100), '', False)
  
  def pauseResumeButton(self, name):
    if name == 'Pause':
      self.run_gcode("M25", '')
    else:
      popup = Factory.DuetStopResume()
      popup.open()

  def updateAdjustScreen(self, justOpened):
    self.gui.updateAdjustScreen(self.printerConnection.status, justOpened)

  def changeToExtState(self, change):
    self.printerConnection.changeToEStatus(change)

  def updateFileInfo(self):
    self.printerConnection.updateFileInfo()
    return self.printerConnection.fileInfo

  def update(self, dt):
    newPeriod = 0
    if not self.printerConnection.connected:
      newPeriod = self.gui.updateStatus('CX', self.printerConnection.extStatus, self.updateFileInfo)
      self.printerConnection.connect()
      # print("STATUS")
      # print(self.printerConnection.status)
      # print("ESTATUS")
      # print(self.printerConnection.extStatus)
      # print("PSTATUS")
      # print(self.printerConnection.printStatus)
      # print("CONFIG")
      # print(self.printerConnection.config)
    else:
      self.proba = self.printerConnection.status['coords']['xyz'][2]
      newPeriod = self.gui.updateStatus(self.printerConnection.status['status'], self.printerConnection.extStatus, self.updateFileInfo)
    if newPeriod > 0: #update period change requested
      Clock.unschedule(self.event)
      self.event = Clock.schedule_interval(self.update, newPeriod)
      self.printerConnection.changeUpdateInterval(newPeriod*1000)
    

    if self.printerConnection.connected:
      self.gui.updateScreen(self.printerConnection.status, self.printerConnection.printStatus, self.printerConnection.extStatus, self.printerConnection.updateEStatus, self)
  

  def on_stop(self):
    self.printerConnection.disconnect()

  def build(self):
    self.printerConnection = DWCConnection(URL, PASSWD, connect = False, useExtStatus = False)
    
    self.gcodeFs = DuetFs(self.printerConnection, '/gcodes')
    self.macroFs = DuetFs(self.printerConnection, '/macros')

    self.gui = DuetMenuMainScreen()
    
    self.event = Clock.schedule_interval(self.update, 1)

    return self.gui

if __name__ == '__main__':
  DuetMenuApp().run()
