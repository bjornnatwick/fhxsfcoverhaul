'''
    Skellig
    DeltaV SFC Overhaul Tool
    Rev: 0.0
    
    This tool takes an fhx file and builds a new fhx file with the following updates:
     - Updates positions of steps and transitions
     - Updates size of steps
     - Updates transition expressions containing pending confirms reference
     - Updates delay expressions referencing action state complete
     - Renames steps, actions, and transitions
'''

#Importing python libraries
import pandas as pd
import fhxutilities as util
from time import strftime

#Importing config files
import fhxconstants as const

#Declare constants
if True:
    XPOS, YPOS, HEIGHT, WIDTH = const.XPOS, const.YPOS, const.HEIGHT, const.WIDTH
    STEP, TRANSITION = const.STEP, const.TRANSITION
    TYPE, OBJS = const.TYPE, const.OBJS
    CLASSES, NAMED_SETS, FB_DEF, FBS = const.CLASSES, const.NAMED_SETS, const.FB_DEF, const.FBS
    
    INIT_STEP_POS = const.INIT_STEP_POS
    BRANCH_DIST, TP_BRANCH_DIST = const.BRANCH_DIST, const.TP_BRANCH_DIST
    
    
    sfcID = '  SFC_ALGORITHM'
    
#Prompt for module file name
fileName = input('\nEnter name of the DeltaV Export (.fhx) file without file extension.\n') + '.fhx'

#Save start time
startTime = {'Hours':int(strftime("%H")),
             'Minutes':int(strftime("%M")),
             'Seconds':int(strftime("%S"))}

#Build list of strings from file
fhxLines = util.BuildLinesFromFhx(fileName)

numOfLines = len(fhxLines)

#Save sections of fhx as paragraph objects
[classes, namedSets, fbDefinitions, fbInstances] = util.SaveParagraphs(fhxLines, [CLASSES, NAMED_SETS, FB_DEF, FBS])

#Build named set dictionary
namedSetMap = util.BuildNamedSetData(fhxLines, namedSets)

#Builds class info and command composite mapping dataframe
classCompMap = util.BuildClassCompData(fhxLines, classes, namedSetMap, fbInstances)

print('\nDo you want to update the following sfc function blocks? Enter "Yes" to continue, or "No" to skip.')

fbDefinitions.reverse()
for fb in fbDefinitions:
    
    #Build string for fb
    lines = '\n'.join(fhxLines[fb.idx: fb.idx + fb.size])
    
    #Skip if not sfc algorithm
    if sfcID not in lines:
        continue
    
    #Set composite name or module/command name
    fbName = fb.name
    
    #Skip if function block not used by any classes
    if fbName in const.FBS_TO_SKIP:
        continue
    
    #If function block is embedded, then find command name where fb is used
    if fbName[:2] == '__' and fbName[-2:] == '__':
        
        #Skip if function block is not a linked composite or used in phase or EM command
        if fbName not in list(classCompMap.keys()):
            continue
        
        names = []
        command = classCompMap[fbName]['Command']
        
        for name in classCompMap[fbName]['Name'].split(', '):
            names.append(name + '/' + command)
        
        fbName = ', '.join(names)
    
    #Prompt user to update command
    answer = input(f'{fbName}: ').lower()
    
    #Skip command if answer is no
    if answer != 'yes' and answer != 'y':
       continue
    
    #Update function block time by one to prevent DeltaV from skipping fb upon import
    util.IncrementTime(fhxLines, fb.idx)
    
    #Build step and transition data
    objMap = util.BuildStepTranData(lines, fb.idx)
    
    '''
    This section builds branch objects and positions.
    '''
    #Build branches
    initStep = util.FindInitStep(lines)
    
    branchMap = util.BuildBranch(initStep, {XPOS: INIT_STEP_POS[0], YPOS: INIT_STEP_POS[1]}, objMap)
    
    #Determine task pointer branches
    util.UpdateTaskPointerBranches(branchMap, classCompMap, fb.name)
    
    #Move branches within parallel branches to opposite side
    util.MoveBranchesWithinParallel(branchMap)
    
    #Shift main branch down if parallel branches are longer
    util.ShiftBranchesLongParallel(branchMap)
    
    #Shift branches to prevent collisions
    util.ShiftBranchesPreventCollisions(branchMap)
    
    #Shift task pointer branches
    branchNumbers = util.BranchNumbers(branchMap)
    shiftDistance = TP_BRANCH_DIST - BRANCH_DIST
    
    for branch in branchNumbers:
        if branchMap[branch][TYPE] == 'Right Task Pointer':
            branchesToShift = [branch] + branchMap[branch]['Right Branches']
            
            for branchToShift in branchesToShift:
                util.ShiftBranch(branchMap, branchToShift, 'Right', shiftDistance)
    
        if branchMap[branch][TYPE] == 'Left Task Pointer':
            branchesToShift = [branch] + branchMap[branch]['Left Branches']
            
            for branchToShift in branchesToShift:
                util.ShiftBranch(branchMap, branchToShift, 'Left', shiftDistance)
    
    #Shift all branches based on farthest left branch
    BranchXPos = lambda branchNum: branchMap[branchNum][XPOS]
    shiftDistance = INIT_STEP_POS[0] - min(map(BranchXPos, branchNumbers))
    
    if shiftDistance:
        util.ShiftBranch(branchMap, 1, 'Right', shiftDistance)
    
    '''
    This section writes branch object position data to fhx lines and 
    updates segment positions.
    '''
    #Update object dictionary positions from branch dictionary
    for branchNum in branchNumbers:
        branch = branchMap[branchNum]
        
        util.UpdateStepTranPositions(objMap, branch)
    
    #Updates line segment positions
    util.UpdateStepTranSegments(objMap, branchMap)
    
    #Writes object data to fhx lines
    util.UpdateLines(fhxLines, objMap)
    
    #Reset branch number
    util.ResetBranchNum()
    
    '''
    This section renames the steps, actions, and transitions. It is required to rebuild object and 
    action data because line numbers might changed have previous sections.
    '''
    #Rebuild string for fb
    lines = '\n'.join(fhxLines[fb.idx: fb.idx + fb.size])
    
    #Rebuild step, action, and transition data
    objMap = util.BuildStepTranData(lines, fb.idx)
    actMap = util.BuildActionData(lines, objMap, fb.idx)
    
    #Build new step, action, and transition names
    newObjNames = util.BuildNewStepTranNames(branchMap, classCompMap, fb.name, objMap)
    newActNames = util.BuildNewActionNames(actMap)
    
    #Rename steps, actions, and transitions if required (order is important)
    util.RenameActions(fhxLines, newActNames, actMap, objMap)
    util.RenameStepsTransitions(fhxLines, newObjNames, objMap, fb.idx, fb.size)
    
    '''
    This section adds an action in each step to update step index.
    '''
    #Rebuild step, action, and transition data
    objMap = util.BuildStepTranData(lines, fb.idx)
    actMap = util.BuildActionData(lines, objMap, fb.idx)
    
    #Add action to every step
    util.BuildStepIndexActions(fhxLines, objMap)
    
    '''
    This section updates transition pending confirms and delay action complete expressions.
    WARNING: this section may add or delete rows in fhx lines. This could interfere with
    prior index. Thus, this section should always execute last.
    '''
    #Rebuild string for fb
    lines = '\n'.join(fhxLines[fb.idx: fb.idx + fb.size])
    
    #Rebuild step, action, and transition data
    objMap = util.BuildStepTranData(lines, fb.idx)
    actMap = util.BuildActionData(lines, objMap, fb.idx)
    
    #Update transition expressions
    util.UpdateTranExp(fhxLines, objMap)
    
    #Update action delay expressions
    util.UpdateDelayExp(fhxLines, actMap)
    
#Build output file name
fileName = fileName[:-4] + '_SFCsArranged_' + strftime("%Y%m%d-%H%M%S") + '.fhx'

#Build output file
with open(fileName, 'w', encoding='utf-16-le') as file:
    file.write('\n'.join(fhxLines))

#Final message
print(f'\nDeltaV export (.fhx) file built called "{fileName}".')