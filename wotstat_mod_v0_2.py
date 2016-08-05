#!/usr/bin/python
# -*- coding: utf-8 -*-
import BigWorld
import AccountCommands
import ArenaType
import datetime
import json
import threading
import httplib
from gui.login import g_loginManager
from Account import Account
from account_helpers import BattleResultsCache
from items import vehicles as vehiclesWG
from messenger.formatters.service_channel import BattleResultsFormatter
from Queue import Queue
from debug_utils import *

GENERAL = 0
BY_TANK = 1


class SessionStatistic(object):

    def __init__(self):
        self.page = GENERAL
        self.queue = Queue()
        self.loaded = False
        self.battleStats = {}
        self.expectedValues = {}
        self.values = {}
        self.battles = []
        self.playerName = ''
        self.playerAccount = ''
        self.startDate = None
        self.battleResultsAvailable = threading.Event()
        self.battleResultsAvailable.clear()
        self.battleResultsBusy = threading.Lock()
        self.thread = threading.Thread(target=self.mainLoop)
        self.thread.setDaemon(True)
        self.thread.start()


    def load(self):

        if self.loaded and self.playerName == BigWorld.player().name:
            return
        self.loaded = True
        self.battles = []
        self.playerName = BigWorld.player().name
        self.loaded = False

    def readConfig(self):
        pass

    def getWorkDate(self):
        return datetime.date.today().strftime('%Y-%m-%d') \
            if datetime.datetime.now().hour >= self.config.get('dailyAutoResetHour', 4) \
            else (datetime.date.today() - datetime.timedelta(days = 1)).strftime('%Y-%m-%d')

    def save(self, data):
#        dataJson = dictToJson(battle)
#        print dataJson
        self.httpConnectoin(self.dictToJson(data))


    def battleResultsCallback(self, arenaUniqueID, responseCode, value = None, revision = 0):
        if responseCode == AccountCommands.RES_NON_PLAYER or responseCode == AccountCommands.RES_COOLDOWN:
            BigWorld.callback(1.0, lambda: self.queue.put(arenaUniqueID))
            self.battleResultsBusy.release()
            @!( 'return 1')
            return
        if responseCode < 0:
            self.battleResultsBusy.release()
            @!('return 2')
            return
        arenaTypeID = value['common']['arenaTypeID']
        arenaType = ArenaType.g_cache[arenaTypeID]
        personal = value['personal'].itervalues().next()
        vehicleCompDesc = personal['typeCompDescr']
        vt = vehiclesWG.getVehicleType(vehicleCompDesc)
        result = 1 if int(personal['team']) == int(value['common']['winnerTeam'])\
            else (0 if not int(value['common']['winnerTeam']) else -1)
        place = 1
        arenaUniqueID = value['arenaUniqueID']
        squadsTier = {}
        vehicles = value['vehicles']
        for vehicle in vehicles.values():
            pTypeCompDescr = vehicle[0]['typeCompDescr']
            if pTypeCompDescr is not None:
                pvt = vehiclesWG.getVehicleType(pTypeCompDescr)
                tier = pvt.level
                if set(vehiclesWG.VEHICLE_CLASS_TAGS.intersection(pvt.tags)).pop() == 'lightTank' and tier > 5:
                    tier += 1
                squadId = value['players'][vehicle[0]['accountDBID']]['prebattleID']
                squadsTier[squadId] = max(squadsTier.get(squadId, 0), tier)
            if personal['team'] == vehicle[0]['team'] and \
                personal['originalXP'] < vehicle[0]['xp']:
                place += 1
        battleTier = 11 if max(squadsTier.values()) == 10 and min(squadsTier.values()) == 9 \
            else max(squadsTier.values())
        proceeds = personal['credits'] - personal['autoRepairCost'] -\
                   personal['autoEquipCost'][0] - personal['autoLoadCost'][0]
        tmenXP = personal['tmenXP']
        if 'premium' in vt.tags:
            tmenXP = int(1.5*tmenXP)
        battle = {
            'playerName': BigWorld.player().name,
            'playerAccount': g_loginManager.getPreference('login'),
            'idNum': vehicleCompDesc,
            'map': arenaType.geometryName,
            'vehicle': vt.name.replace(':', '-'),
            'tier': vt.level,
            'result': result,
            'damage': personal['damageDealt'],
            'frag': personal['kills'],
            'spot': personal['spotted'],
            'def': personal['droppedCapturePoints'],
            'cap': personal['capturePoints'],
            'shots': personal['shots'],
            'hits': personal['directHits'],
            'pierced': personal['piercings'],
            'xp': personal['xp'],
            'originalXP': personal['originalXP'],
            'freeXP': personal['freeXP'],
            'place': place,
            'credits': proceeds,
            'gold': personal['gold'] - personal['autoEquipCost'][1] - personal['autoLoadCost'][1],
            'battleTier': battleTier,
            'assist': personal['damageAssistedRadio'] + personal['damageAssistedTrack'],
            'assistRadio': personal['damageAssistedRadio'],
            'assistTrack': personal['damageAssistedTrack']
        }
        extended = {
            'vehicle': battle['vehicle'],
            'map': battle['map'],
            'result': result,
            'autoRepair': personal['autoRepairCost'],
            'autoEquip': personal['autoEquipCost'][0],
            'autoLoad': personal['autoLoadCost'][0],
            'tmenXP': tmenXP
        }

        @!( 'battle')
        @!( battle)
        @!( 'extended')
        @!( extended)
        self.save(battle)
        self.battleResultsBusy.release()

    def reset(self):
        self.page = GENERAL
        self.startDate = self.getWorkDate()
        self.battles = []
#        self.save()

    def mainLoop(self):
        while True:
            arenaUniqueID = self.queue.get()
            self.battleResultsAvailable.wait()
            self.battleResultsBusy.acquire()
            BigWorld.player().battleResultsCache.get(arenaUniqueID,lambda resID, value: self.battleResultsCallback(arenaUniqueID, resID, value, None))


    def dictToJson(self,dictData):
        dataJson = json.dumps(dictData,  separators=(',', ': '),ensure_ascii = False, encoding='utf-8')
        return dataJson


    def httpConnectoin(self,dataSend):
        headers = {"Content-type": "application/json"}
        conn = httplib.HTTPConnection("localhost",9000)
        conn.request("POST", "/sendStat", dataSend, headers)
        response = conn.getresponse()
#        @!(response.status, response.reason)
#    	data = response.read()
        conn.close()
        

old_onBecomePlayer = Account.onBecomePlayer

def new_onBecomePlayer(self):
    old_onBecomePlayer(self)
    stat.battleResultsAvailable.set()
    stat.load()

Account.onBecomePlayer = new_onBecomePlayer


old_onBecomeNonPlayer = Account.onBecomeNonPlayer

def new_onBecomeNonPlayer(self):
    stat.battleResultsAvailable.clear()
    old_onBecomeNonPlayer(self)

Account.onBecomeNonPlayer = new_onBecomeNonPlayer


old_brf_format = BattleResultsFormatter.format

def new_brf_format(self, message, *args):
    result = old_brf_format(self, message, *args)
    @!('new_brf_format')
    arenaUniqueID = message.data.get('arenaUniqueID', 0)
    stat.queue.put(arenaUniqueID)
    return result

BattleResultsFormatter.format = new_brf_format

stat = SessionStatistic()
