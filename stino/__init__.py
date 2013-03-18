#-*- coding: utf-8 -*-
# stino/__init__.py

import sublime

import utils
import stpanel
import const
import osfile
import language
import smonitor
import arduino
import stmenu
import actions

log_panel = stpanel.STPanel()
serial_listener = smonitor.SerialPortListener()
cur_language = language.Language()
arduino_info = arduino.Arduino()
cur_menu = stmenu.STMenu(cur_language, arduino_info)
serial_port_in_use_list = []
serial_port_monitor_dict = {}