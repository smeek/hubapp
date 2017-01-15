#!rules.py

from datetime import datetime
from datetime import timedelta
from pathlib import Path
from subprocess import call
# App-specific Python modules
import events
import log
import hubapp
import devices
import zcl
import variables

if __name__ == "__main__":
    hubapp.main()

rulesFilename = "rules.txt"

# Example rules.txt
# if HallwayPir==active do SwitchOn HallwayLight for 120
# if HallwayBtn==TOGGLE do Toggle HallwayLight
# if HallwayPir==active and 16:00<time<23:59 do SwitchOn HallwayLight for 120
# if HallwayPir==active and 0:00<time<1:00 do SwitchOn HallwayLight for 120
# if StairPir==active and 16:00<time<20:00 do SwitchOn StairLight for 120
# if StairPir==active and 20:00<time<23:00 do Dim StairLight to 0.15 for 120
#if DoorBell==TOGGLE and 7:00<time<20:59 do Play Westminster-chimes.mp3
#if DoorBell==TOGGLE and 21:00<time<23:59 do email spikey@rosepip.com Out of hours doorbell

# Note spaces used to separate each item.
# Syntax is "if <condition> do <action>[ for <duration>]"

def EventHandler(eventId, eventArg):
    if eventId == events.ids.TRIGGER:
        devIdx = devices.GetIdx(eventArg[1]) # Lookup device from network address in eventArg[1]
        userName = devices.GetVal(devIdx, "UserName")
        zoneType = devices.GetAttrVal(devIdx, zcl.Cluster.IAS_Zone, zcl.Attribute.Zone_Type) # Device type
        if zoneType != None:
            #log.log("DevId: "+eventArg[1]+" has type "+ zoneType)
            if zoneType == zcl.Zone_Type.Contact:
                if int(eventArg[3], 16) & 1: # Bottom bit indicates alarm1
                    if userName:
                        Run(userName+"==opened") # See if rule exists
                    log.log("Door "+ eventArg[1]+ " opened")
                else:
                    if userName:
                        Run(userName+"==closed") # See if rule exists
                    log.log("Door "+ eventArg[1]+ " closed")
            elif zoneType == zcl.Zone_Type.PIR:
                if userName:
                    Run(userName+"==active") # See if rule exists
                log.log("PIR "+ eventArg[1]+ " active")
            else:
                log.log("DevId: "+ eventArg[1]+" zonestatus "+ eventArg[3])
        else:
            log.fault("Unknown IAS device type for devId "+eventArg[1])
    elif eventId == events.ids.BUTTON:
        devIdx = devices.GetIdx(eventArg[1]) # Lookup device from network address in eventArg[1]
        userName = devices.GetVal(devIdx, "UserName")
        log.log("Button "+ eventArg[1]+ " "+eventArg[0]) # Arg[0] holds "ON", "OFF" or "TOGGLE" (Case might be wrong)
        if userName:
            Run(userName+"=="+eventArg[0]) # See if rule exists

def Run(trigger): # Run through the rules looking to see if we have a match for the trigger
    log.log("Running rule: "+ trigger)
    rulesFile = Path(rulesFilename)
    if rulesFile.is_file():
        with open(rulesFilename) as rules:
            for line in rules:
                rule = ' '.join(line.split()) # Compact multiple spaces into single ones and make each line into a rule
                ruleList = rule.split(" ") # Make each rule into a list
                if ruleList[0] == "if":
                    doIndex = FindItemInList("do", ruleList) # Safely look for "do"
                    if doIndex != None:
                        if ParseCondition(ruleList[1:doIndex], trigger) == True: # Parse condition from element 1 to "do" 
                            Action(ruleList[doIndex+1:]) # Do action
                    # else skip rest of line
                elif ruleList[0] == "do":
                    Action(ruleList[1:])
                # else assume the line is a comment and skip it
            # end of rules
    else:
        log.fault("No " + rulesFilename+" !")

def FindItemInList(item, listToCheck):
    try:
        return listToCheck.index(item)
    except ValueError:
        return None

def ParseCondition(ruleConditionList, trigger):
    subAnswers = ""
    for condition in ruleConditionList:
        if condition == "and":
            subAnswers = subAnswers+" and "
        elif condition == "or":
            subAnswers = subAnswers+" or "
        elif "<time<" in condition:
            sep = condition.index("<time<") # Handle time here
            nowTime = datetime.strptime(datetime.now().strftime("%H:%M"), "%H:%M")
            startTime = datetime.strptime(condition[:sep], "%H:%M")
            endTime = datetime.strptime(condition[sep+6:], "%H:%M")
            if startTime <= nowTime <= endTime:
               subAnswers = subAnswers + "True"
            else:
               subAnswers = subAnswers + "False"
        elif "<=" in condition:
            subAnswers = subAnswers + str(GetConditionResult("<=", condition))
        elif ">=" in condition:
            subAnswers = subAnswers + str(GetConditionResult(">=", condition))
        elif "<" in condition:
            subAnswers = subAnswers + str(GetConditionResult("<", condition))
        elif ">" in condition:
            subAnswers = subAnswers + str(GetConditionResult(">", condition))
        #elif "==" in condition: # Causes confusion with "Pir==active"
        #    subAnswers = subAnswers + str(GetConditionResult("==", condition))
        elif condition == trigger: # Simple match for now
           subAnswers = subAnswers + "True"
        else:
           subAnswers = subAnswers + "False"
    # End of loop
    if eval(subAnswers) == True:
        return True
    else:
        return False

def GetConditionResult(test, condition):
    sep = test in condition # Assume this has already been shown to return a valid answer
    varName = condition[:sep] # Variable must be on the left of the expression
    tstVal = condition[sep+len(test):] # Simple value must be on right
    varVal = variables.Get(varName)
    if varVal != None:
        return eval(varVal + test + tstVal)
    else:
        return False # If we couldn't find the item requested, assume the condition fails(?)

def Action(actList):
    log.log("Action with: "+str(actList))
    action = actList[0]
    if action == "Log":
        log.log("Rule says Log event for "+' '.join(actList[1:]))
    elif action == "Play":
        filename = "Sfx/"+actList[1]
        call(["omxplayer", "-o", "local", filename])
    elif action == "email": # First arg is recipient, remainder are body of the text.  Fixed subject
        cmdList = ["echo", "\""+' '.join(actList[2:])+"\"", "|", "mail", "-s", "\"Alert from IoT-Hub\"", actList[1]]
        cmdStr = " ".join(cmdList)
        call(cmdStr, shell=True)
    else: # Must be a command for a device
        devIdx = devices.GetIdxFromUserName(actList[1]) # Second arg is username for device
        if devIdx == None:
            log.fault("Device "+actList[0]+" from rules.txt not found in devices")
        else:
            if action == "SwitchOn":
                devices.SwitchOn(devIdx)
                if len(actList) > 3:
                    if actList[2] == "for":
                        SetOnDuration(devIdx, int(actList[3],10))
            elif action == "SwitchOff":
                devices.SwitchOff(devIdx)
            elif action == "Toggle":
                devices.Toggle(devIdx)
            elif action == "Dim" and actList[2] == "to":
                devices.Dim(devIdx,float(actList[3]))
                if len(actList) > 5:
                    if actList[4] == "for":
                        SetOnDuration(devIdx, int(actList[5],10))
            else:
                log.log("Unknown action: "+action +" for device: "+devices.GetUserName(devIdx))

def SetOnDuration(devIdx, durationS):
    if durationS>0: # Duration of 0 means "Stay on forever"
        log.log("Switching off after "+str(durationS))
        devices.SetTempVal(devIdx, "SwitchOff@", datetime.now()+timedelta(seconds=durationS))

