import z3, z3util
import ast
import logging
from copy import copy, deepcopy
import pyState.BinOp, pyState.Pass, pyState.While, pyState.Break
import random
import os.path
import importlib
from types import ModuleType
import ntpath
import pyState.z3Helpers

# The current directory for running pySym
SCRIPTDIR = os.path.dirname(os.path.abspath(__file__))

logger = logging.getLogger("State")

def z3_bv_to_int(x):
    # Convers BitVec to Int in the solver
    # example: s.add(q == to_int(z)) where q == IntSort and z == BitVecSort
    return z3.ArithRef(z3.Z3_mk_bv2int(x.ctx_ref(), x.as_ast(), 0), x.ctx)

def z3_int_to_bv(x):
    # Converts Int to BV
    # Note, that we need a default length here for the BitVec... Assuming 128 for now
    # TODO: Figure out better way of handling the BitVec length
    return z3.BitVecRef(z3.Z3_mk_int2bv(x.ctx_ref(),128,x.as_ast()))


# Create small class for keeping track of return values
class ReturnObject:
    def __init__(self,retID):
        self.retID = retID

# I feel bad coding this but I can't find a better way atm.
def replaceObjectWithObject(haystack,fromObj,toObj,parent=None):
    """
    Find instance of fromObj in haystack and replace with toObj
    Terrible hack here, but this is used to ensure we know which function return is ours
    Returns True on success and False on fail
    """
    parent = haystack if parent is None else parent
    
    # If we found the object
    if haystack == fromObj:
        parent[parent.index(fromObj)] = toObj
        return True
    
    if type(haystack) == list:
        for x in haystack:
            if replaceObjectWithObject(x,fromObj,toObj,haystack):
                return True
    
    try:
        fields = haystack._fields
        if len(fields) == 0:
            return False
    except:
        return False

    for field in fields:
        if getattr(haystack,field) == fromObj:
            setattr(haystack,field,toObj)
            return True

        if replaceObjectWithObject(getattr(haystack,field),fromObj,toObj,haystack):
            return True
    
    return False



def duplicateSort(obj):
    """
    Input:
        obj = z3 object to duplicate kind (i.e.: z3.IntSort())
    Action:
        Figure out details of the object and make duplicate sort
    Return:
        Duplicate Sort object
    """
    
    if type(obj) in [z3.IntNumRef,z3.RatNumRef,z3.ArithRef]:
        kind = obj.sort_kind()
     
    else:
        # Lookup Kind
        kind = obj.kind()
    
    kindTable = {
        z3.Z3_INT_SORT: z3.IntSort(),
        z3.Z3_REAL_SORT: z3.RealSort(),
        z3.Z3_BOOL_SORT: z3.BoolSort()
    }
    
    if kind in kindTable:
        return kindTable[kind]

    elif kind == z3.Z3_ARRAY_SORT:
        return z3.ArraySort(obj.domain().kind(),obj.range.kind())

    elif kind == z3.Z3_BV_SORT:
        return z3.BitVecSort(obj.size())
    
    else:
        err = "duplicateSort: unable to determine object sort '{0}'".format(obj)
        logger.error(err)
        raise Exception(err)



def get_all(f,rs=[]):
    """
    >>> x,y = Ints('x y')
    >>> a,b = Bools('a b')
    >>> get_all(Implies(And(x+y==0,x*2==10),Or(a,Implies(a,b==False))))
    [x, y, a, b]
    """
    if __debug__:
        assert z3util.is_expr(f)

    if z3util.is_const(f):
        return z3util.vset(rs + [f],str)

    else:
        for f_ in f.children():
            rs = get_all(f_,rs)

        return z3util.vset(rs,str)

def hasRealComponent(expr):
    """
    Input:
        expr = expression object
    Action:
        Checks if expression contains a real/non-int value or variable
    Returns:
        True if it has real componenet, False otherwise
    """
    return max([False if type(x) not in [z3.ArithRef, z3.RatNumRef] else x.is_real() for x in get_all(expr)])


class State():
    """
    Defines the state of execution at any given point.
    """

    """
    localVars and globalVars are dicts containing variables and their constraint expressions
    
    localVars = {
        <contextID> : {
            'x': {
                'varType': "z3.IntSort()", # Eval string to re-create the object's type on the fly. This is because z3 kept on crashing everything :-(
                'count': 0 # This helps us keep track of Static Single Assignment forms
            }
        }
    }
    """
    
    def __init__(self,path=None,localVars=None,globalVars=None,solver=None,ctx=None,functions=None,simFunctions=None,retVar=None,callStack=None,backtrace=None,retID=None,loop=None):
        """
        (optional) path = list of sequential actions. Derived by ast.parse. Passed to state.
        (optional) backtrace = list of asts that happened before the current one
        """
 
        self.path = [] if path is None else path
        self.ctx = 0 if ctx is None else ctx
        self.localVars = {self.ctx: {}, 1: {}} if localVars is None else localVars
        self.globalVars = {} if globalVars is None else globalVars
        self.solver = z3.Solver() if solver is None else solver
        # functions = {'func_name': ast.function declaration}
        self.functions = {} if functions is None else functions
        self.simFunctions = {} if simFunctions is None else simFunctions
        self.retVar = self.getZ3Var('ret',increment=True,varType=z3.IntSort(),ctx=1) if retVar is None else retVar
        # callStack == list of dicts to keep track of state (i.e.: {'path': [1,2,3],'ctx': 1, 'ast_call': <ast call object>}
        self.callStack = [] if callStack is None else callStack
        self.backtrace = [] if backtrace is None else backtrace
        # Keep track of what our return ID is
        self.retID = retID
        self.loop = loop
        
        # Initialize our known functions if this is the first time through
        if backtrace is None:
            self._init_simFunctions()
        
    def lineno(self):
        """
        Returns current line number. If returning from a call, returns the return line number
        Returns None if the program is done
        """
        
        # Return current lineno if exists
        if len(self.path) > 0:
            return self.path[0].lineno

        # Check if we're going back to the start of the loop
        if self.loop:
            return self.loop.body[0].lineno
        
        # Check up the call tree for instruction
        for cs in self.callStack[::-1]:
            if len(cs['path']) > 0:
                return cs['path'][0].lineno
            # If we're returning to start the loop anew
            if cs['loop']:
                return cs['loop'].lineno
        
        # Looks like we're done with the program
        return None
    
    def popCallStack(self):
        """
        Input:
            Nothing
        Action:
            Pops from the call stack to the run stack. Adds call to completed state
        Returns:
            True if pop succeeded, False if there was nothing left to pop
        """

        # Check if we have somewhere to return to
        if len(self.callStack) == 0:
            return False

        # Pop the callStack back on to the run queue
        cs = self.callStack.pop()
        self.path = cs["path"]
        self.ctx = cs["ctx"]
        self.retID = cs["retID"]
        self.loop = cs["loop"]
        
        return True

    def step(self):
        """
        Move the current path forward by one step
        Note, this actually makes a copy/s and returns them. The initial path isn't modified.
        Returns: A list of paths or empty list if the path is done 
        """
        # Adding sanity checks since we are not supposed to change during execution
        h = hash(self)
        
        logger.debug("step:\n\tpath = {0}\n\tcallStack = {1}\n\tctx = {2}\n\tretID = {3}\n\tsolver = {4}\n\tloop = {5}\n".format(self.path,self.callStack,self.ctx,self.retID,self.solver,self.loop))

        # More cleanly resolve instructions
        # TODO: Move this somewhere else... Moving it to the top of State introduced "include hell" :-(
        instructions = {
            ast.Assign: pyState.Assign,
            ast.AugAssign: pyState.AugAssign,
            ast.FunctionDef: pyState.FunctionDef,
            ast.Expr: pyState.Expr,
            ast.Pass: pyState.Pass,
            ast.Return: pyState.Return,
            ast.If: pyState.If,
            ast.While: pyState.While,
            ast.Break: pyState.Break
            }

        # Return initial return state
        state = self.copy()
        
        # Check if we're out of instructions
        if len(state.path) == 0:
            # If we're in a loop, time to re-evaluate it
            if state.loop:
                state.path = [deepcopy(state.loop)]
            # If we're not in a loop, try to pop up one on the stack
            elif not state.popCallStack():
                return []

        # Get the current instruction
        inst = state.path[0]

        # Generically handle any instruction we know about
        if type(inst) in instructions:
            ret_states = instructions[type(inst)].handle(state,inst)

        else:
            err = "step: Unhandled element of type {0} at Line {1} Col {2}".format(type(inst),inst.lineno,inst.col_offset)
            logger.error(err)
            raise Exception(err)

        # Move instruction to the done pile :-)
        for state in ret_states:
            state.backtrace.insert(0,inst)

        # Assert we haven't changed
        assert h == hash(self)
        
        # Return the paths
        return ret_states


    def Return(self,retElement):
        """
        Input:
            retElement = ast.Return element
        Action:
            Set return variable appropriately and remove the rest of the instructions in the queue
        Returns:
            Nothing for now
        """
        obj = retElement.value
        
        obj = self.resolveObject(obj)
        
        # If this is a ReturnObject, forward it on
        if type(obj) == ReturnObject:
            return obj
        
        # Check for int vs real
        if hasRealComponent(obj):
            retVar = self.getZ3Var('ret{0}'.format(self.retID),varType=z3.RealSort(),ctx=1,increment=True)
        
        else:
            retVar = self.getZ3Var('ret{0}'.format(self.retID),varType=z3.IntSort(),ctx=1,increment=True)
        
        # Add the constraint
        self.addConstraint(retVar == obj)
        
        # Remove the remaining instructions in this function
        self.path = []


    def Call(self,call,retID=None,func=None):
        """
        Input:
            call = ast.Call object
            (optional) retID = ID of the return object
            (optional) func = resolved function for Call (i.e.: state.resolveCall(call)). This is here to remove duplicate calls to resolveCall from resolveObject
        Action:
            Modify state in accordance w/ call
        Returns:
            ReturnObject the describes this functions return var
        """
        assert type(call) == ast.Call
        logger.debug("Call: Setting up for Call to {0}".format(call.func.id))
        
        # Resolve the call
        func = self.resolveCall(call) if func is None else func
        logger.debug("Call: Resolved Function to {0}".format(func))
        
        # If the body is empty, don't actually call, just return []
        if len(func.body) == 0:
            logger.warn("Just made call to empty function {0}".format(funcName))
            return []
        
        if len(func.args.args) - len(func.args.defaults) > len(call.args):
            err = "call: number of arguments don't match expected, line {0} col {1}".format(call.lineno,call.col_offset)
            logger.error(err)
            raise Exception(err)

        
        # Grab a new context
        oldCtx = self.ctx
        # TODO: Check for ctx collision here from previous ctx... Or just rework the whole ctx ID thing
        self.ctx = hash(call.func.ctx)
        
        logger.debug("Call: Old CTX = {0} ... New CTX = {1}".format(oldCtx,self.ctx))
        
        ######################
        # Populate Variables #
        ######################

        # Create local vars dict
        self.localVars[self.ctx] = {}
        
        # If there are arguments, fill them in
        for i in range(len(call.args)):
            caller_arg = self.resolveObject(call.args[i],ctx=oldCtx)
            dest_arg = self.getZ3Var(func.args.args[i].arg,increment=True,varType=duplicateSort(caller_arg))
            self.addConstraint(dest_arg == caller_arg)
            logger.debug("Call: Setting argument {0} = {1}".format(dest_arg,caller_arg))
        
        # Grab any unset vars
        unsetArgs = func.args.args[len(call.args):]
        
        # Handle any keyword vars
        for i in range(len(call.keywords)):
            # Make sure this is a valid keyword
            if call.keywords[i].arg not in [x.arg for x in unsetArgs]:
                err = "call: Attempting to set invalid keyword '{0}' line {1} col {2}".format(call.keywords[i].arg,call.keywords[i].arg.lineno,call.keywords[i].arg.col_offset)
                logger.error(err)
                raise Exception(err)
            caller_arg = self.resolveObject(call.keywords[i].value,ctx=oldCtx)
            dest_arg = self.getZ3Var(call.keywords[i].arg,increment=True,varType=duplicateSort(caller_arg)) 
            self.addConstraint(dest_arg == caller_arg)
            # Remove arg after it has been satisfied
            unsetArgs.remove([x for x in unsetArgs if x.arg == call.keywords[i].arg][0])
            logger.debug("Call: Setting keyword argument {0} = {1}".format(dest_arg,caller_arg))


        # Handle any defaults
        for arg in unsetArgs:
            argIndex = func.args.args.index(arg) - (len(func.args.args) - len(func.args.defaults))
            caller_arg = self.resolveObject(func.args.defaults[argIndex],ctx=oldCtx)
            dest_arg = self.getZ3Var(arg.arg,increment=True,varType=duplicateSort(caller_arg))
            self.addConstraint(dest_arg == caller_arg)
            logger.debug("Call: Setting default argument {0} = {1}".format(dest_arg,caller_arg))

       
        ####################
        # Setup Return Var #
        ####################
 
        # ctx of 1 is our return ctx
        # self.retVar = self.getZ3Var('ret',increment=True,varType=z3.IntSort(),ctx=1)
        # Generate random return ID
        oldRetID = self.retID
        self.retID = hash(call) if retID is None else retID

        #################
        # Clearout Loop #
        #################
        # If we are calling something, save off our loop, but clear it out in current path
        oldLoop = self.loop
        self.loop = None
        
        ##################
        # Save CallStack #
        ##################
        cs = deepcopy(self.path)
        if len(cs) > 0:
            self.pushCallStack(path=cs,ctx=oldCtx,retID=oldRetID,loop=oldLoop)
        
        self.path = func.body
        logger.debug("Call: Saved callstack: {0}".format(self.callStack))
        logger.debug("Call: Set new path {0}".format(self.path))
        
        # Return our ReturnObject
        return ReturnObject(self.retID)

    def pushCallStack(self,path=None,ctx=None,retID=None,loop=None):
        """
        Save the call stack with given variables
        Defaults to current variables if none given
        """

        self.callStack.append({
            'path': path if path is not None else self.path,
            'ctx': ctx if ctx is not None else self.ctx,
            'retID': retID if retID is not None else self.retID,
            'loop': loop if loop is not None else self.loop,
        })

    def _init_simFunctions(self):
        """
        Input:
            Nothing
        Action:
            Initializes hooked functions (i.e.: pyState/functions/.)
        Returns:
            Nothing
        """
        # Base simFunction directory
        BASE = os.path.join(SCRIPTDIR,"functions")
        
        # Walk through functions
        for subdir, dirs, files in os.walk(BASE):
            if "__pycache__" in subdir:
                continue

            for f in files:
                if f in ['__init__.py'] or not f.endswith(('.py','.pyc','.pyo')):
                    continue

                # TODO: This is messy...
                modName = "." + os.path.join(subdir,f).replace(BASE,"").replace(f,"").strip("/").replace("/",".")
                modName = "" if modName is "." else modName
                modFName = os.path.splitext(f)[0]
                imp = importlib.import_module(('pyState.functions' + modName + "." + modFName).replace("..","."))
                self.registerFunction(imp,modName,True)


    def registerFunction(self,func,base=None,simFunction=None):
        """
        Input:
            func = ast func definition
            (optional) base = base path to import as (i.e.: "telnetlib" if importing "telnetlib.Telnet")
            (optional) simFunction = Boolean if this should be treated as a simFunction and therefore not handled symbolically. Defaults to False.
        Action:
            Register's this function as being known to this state
        Returns:
            Nothing
        """
        assert type(func) in [ast.FunctionDef,ModuleType]
        assert type(base) in [type(None),str]
        assert type(simFunction) in [type(None),bool]
        
        simFunction = False if simFunction is None else simFunction
        
        # Resolve the optional base
        base = "" if base is None else base
        # Add the end "." if needed
        base = base + "." if base is not "" and not base.endswith(".") else base
        
        # If this is a normal function
        if not simFunction:
            assert type(func) is ast.FunctionDef
            funcName = base + func.name
            logger.debug("registerFunction: Registering function '{0}'".format(funcName))
            self.functions[funcName] = func
        
        # This must be a simFunction
        else:
            assert type(func) is ModuleType
            funcName = func.__package__.replace("pyState.functions","") + "." + os.path.splitext(ntpath.basename(func.__file__))[0]
            funcName = funcName.lstrip(".")
            logger.debug("registerFunction: Registering simFunction '{0}'".format(funcName))
            self.simFunctions[funcName] = func

    def resolveCall(self,call):
        """
        Input:
            call = ast.Call object
        Action:
            Determine correct ast.func object
        Returns:
            ast.func block
        """
        
        # If this is a local context call (i.e.: test())
        if type(call.func) == ast.Name:
            funcName = call.func.id
        
        # If this is an attr form (i.e.: telnetlib.Telnet())
        elif type(call.func) == ast.Attribute:
            funcName = call.func.value.id + "." + call.func.attr
            
        else:
                err = "resolveCall: unknown call-type object '{0}'".format(type(call))
                logger.error(err)
                raise Exception(err)

        # Give sim functions priority
        if funcName in self.simFunctions:
            return self.simFunctions[funcName]

        # If this function is a known local function, return it
        elif funcName in self.functions:
            return self.functions[funcName]

        else:
            err = "resolveCall: unable to resolve call to '{0}'".format(funcName)
            logger.error(err)
            raise Exception(err)


    def resolveObject(self,obj,parent=None,ctx=None):
        """
        Input:
            obj = Some ast object (i.e.: ast.Name, ast.Num, etc)
                special object "PYSYM_TYPE_RETVAL" (int) will resolve the
                last return value
            (optional) parent = parent node of obj. This is needed for resolving calls
            (optional) ctx = Context other than current to resolve in
        Action:
            Resolve object into something that can be used in a constraint
        Return:
            Resolved object
                ast.Num == int (i.e.: 6)
                ast.Name == z3 Object
                ast.BinOp == z3 expression of BinOp (i.e.: x + y)
        """
        ctx = self.ctx if ctx is None else ctx
        t = type(obj)
        
        if t == ast.Name:
            logger.debug("resolveObject: Resolving object type var named {0}".format(obj.id))
            return self.getZ3Var(obj.id,ctx=ctx)
        
        elif t == ast.Num:
            logger.debug("resolveObject: Resolving object type Num: {0}".format(obj.n))
            # Return real val or int val
            return z3.RealVal(obj.n) if type(obj.n) == float else z3.IntVal(obj.n)
        
        #elif t == ast.Str:
        #    logger.debug("resolveObject: Resolving object type Str: {0}".format(obj.s))
        #    # Return real val or int val
        #    return z3.RealVal(obj.n) if type(obj.n) == float else z3.IntVal(obj.n)
        
        elif t == ast.BinOp:
            logger.debug("resolveObject: Resolving object type BinOp")
            return BinOp.handle(self,obj,ctx=ctx)

        elif t == ReturnObject:
            logger.debug("resolveObject: Resolving return type object with ID: ret{0}".format(obj.retID))
            return self.getZ3Var('ret{0}'.format(obj.retID),ctx=1)

        # Hack-ish solution to handle calls
        elif t == ast.Call:
            # Let's see if this is a real or sim call
            func = self.resolveCall(obj)
            
            # If this is a simFunction
            if type(func) is ModuleType:
                # Simple pass it off to the handler, filling in args as appropriate
                return func.handle(self,*obj.args)
                """
                # If we're returning something, replace the call w/ the return value
                if ret:
                    assert replaceObjectWithObject(self.path[0],obj,ret)
               
                # Ignore return 
                elif ret is None:
                    pass
                
                else:
                    err = "resolveObject: unknown simFunction return object '{0}' from call '{1}'".format(ret,func)
                    logger.error(err)
                    raise Exception(err)
                
                # TODO: Maybe return something here?
                return
                """ 

            # If we get here, we're a normal symbolic function
            else:
                # Create our return object
                retObj = ReturnObject(hash(obj))
            
                # Update state, change call to ReturnObject so we can resolve next time
                assert replaceObjectWithObject(self.path[0],obj,retObj)
                # Change our state, record the return object
                Call.handle(self,obj,retID=retObj.retID)
            
                # Return the ReturnObject back to caller to inform them of the pending call
                return retObj

        else:
            err = "resolveObject: unable to resolve object '{0}'".format(obj)
            logger.error(err)
            raise Exception(err)


    def _varTypeToString(self,varType):
        """
        Input:
            varType = z3 var sort (i.e.: z3.IntSort())
        Action:
            Resolves input type back to it's string (i.e.: "z3.IntSort()")
        Returns:
            String representation of varType
        """
        assert type(varType) in [z3.ArithSortRef,z3.BoolSortRef,z3.BitVecSortRef]
        
        if type(varType) == z3.ArithSortRef:
            if varType.is_real():
                return "z3.RealSort()"
            elif varType.is_int():
                return "z3.IntSort()"
            else:
                raise Exception("Got unknown ArithSortRef type {0}".format(varType))

        elif type(varType) == z3.BoolSortRef:
            if varType.is_bool():
                return "z3.BoolSort()"
            else:
                raise Exception("Got unknown BoolSortRef type {0}".format(varType))

        elif type(varType) == z3.BitVecSortRef:
            return "z3.BitVecSort({0})".format(varType.size())


    def getZ3Var(self,varName,local=True,increment=False,varType=None,previous=False,ctx=None):
        """
        Input:
            varName = Variable name to retrieve Z3 object of
            (optional) local = Boolean if we're dealing with local scope
            (optional) increment = Increment the counter. This is if we want to do
                                   something new with this variable. If variable
                                   does not exist, it will be created in the scope
                                   defined by the "local" param
            (optional) varType = Type of var to create. Used when increment=True
                                 and var cannot be found. (i.e: z3.IntSort())
            (optional) previous = Bool of do you want one that is one older
                                  i.e.: current is x_1, return x_0
            (optional) ctx = context to resolve in if not the current one
        Action:
            Look-up variable
        Returns:
            z3 object variable with given name or None if it cannot be found
        """
        # It's important to look this up since we might not know going in
        # what the variable type is. This keeps track of that state.
        
        # Variable naming convention. Intentionally breaking legal python variable naming conventions
        # <Count><VarName>@<context>
        # example: 07MyVar@1
        
        #TODO: Optimize this
        
        ctx = self.ctx if ctx is None else ctx

        # If we're looking up local variable
        if local:
            if varName in self.localVars[ctx]:
                # Increment the counter if asked
                if increment:
                    self.localVars[ctx][varName]['count'] += 1
                count = self.localVars[ctx][varName]['count']
                # Get previous
                if previous:
                    count -= 1
            
                # Set varType if asked for
                if type(varType) != type(None):
                    self.localVars[ctx][varName]['varType'] = self._varTypeToString(varType)
                
                return z3Helpers.mk_var("{0}{1}@{2}".format(count,varName,ctx),eval(self.localVars[ctx][varName]['varType']))
        
            # If we want to increment but we didn't find it, create it
            elif increment:
                assert type(varType) in [z3.ArithSortRef,z3.BoolSortRef,z3.BitVecSortRef]
                
                # Time to create a new var!
                self.localVars[ctx][varName] = {
                    'count': 0,
                    'varType': self._varTypeToString(varType)
                }
                return z3Helpers.mk_var("{0}{1}@{2}".format(self.localVars[ctx][varName]['count'],varName,ctx),varType)
        
        # Try global
        """
        if varName in self.globalVars:
            # Increment the counter if asked
            if increment:
                self.localVars[varName]['count'] += 1
            count = self.globalVars[varName]['count']
            if previous:
                count -= 1
            
            # Set varType if asked for
            if varType != None:
                self.localVars[varName]['varType'] = self._varTypeToString(varType)
            
            return z3Helpers.mk_var("{0}{1}".format(count,varName),eval(self.globalVars[varName]['varType']))
        """
        
        # We failed :-(
        return None


    def addConstraint(self,constraint):
        """
        Input:
            constraint = A z3 expression to use as a constraint
        Action:
            Add constraint given
        Returns:
            Nothing
        """
        # Sanity checks
        assert "z3." in str(type(constraint))
        
        # Add our new constraint to the solver
        self.solver.add(constraint)
        
        # Using iterative engine
        self.solver.push()
        

    def isSat(self):
        """
        Input:
            Nothing
        Action:
            Checks if the current state is satisfiable
            Note, it uses the local and global vars to create the solver on the fly
        Returns:
            Boolean True or False
        """
        # Get and clear our solver
        s = self.solver

        # Changing how I manage constraints. They're all going into the solver directly now
        # Just need to ask for updated SAT
        return s.check() == z3.sat
        
    def printVars(self):
        """
        Input:
            Nothing
        Action:
            Resolves current constraints and prints viable variables
        Returns:
            Nothing
        """
        # Populate model
        if not self.isSat():
            print("State does not seem possible.")
            return
        
        # Set model
        m = self.solver.model()
        
        # Loop through model, printing out vars
        for var in m:
            print("{0} == {1}".format(var.name(),m[var]))

    def any_int(self,var,ctx=None):
        """
        Input:
            var == variable name. i.e.: "x"
            (optional) ctx = context if not current one
        Action:
            Resolve possible value for this variable
        Return:
            Discovered variable or None if none found
        """
        # Grab appropriate ctx
        ctx = ctx if not None else self.ctx
        
        # Solve model first
        if not self.isSat():
            logger.debug("any_int: No valid model found")
            # No valid ints
            return None

        # Get model
        m = self.solver.model()
        
        # Check if we have it in our localVars
        if self.getZ3Var(var,ctx=ctx) == None:
            logger.debug("any_int: var '{0}' not in known localVars".format(var))
            return None

        var = self.getZ3Var(var,ctx=ctx)
        
        # Try getting the value
        value = m.eval(var)
        
        # Check if we have a known solution
        # Assuming local for now
        if type(value) == z3.ArithRef:
            logger.debug("any_int: var '{0}' not found in solution".format(var))
            # No known solution
            return None

        # Check the type of the value
        if type(value) not in [z3.IntNumRef,z3.BitVecNumRef]:
            err = "any_int: var '{0}' not of type int, of type '{1}'".format(var,type(value))
            logger.error(err)
            raise Exception(err)
        
        # Made it! Return it as an int
        return int(value.as_string(),10)

    """
    def any_num(self,var):
        Input:
            var == variable name. i.e.: "x"
        Action:
            Resolve possible value for this variable
        Return:
            Discovered variable or None if none found
            This will attempt to discover the correct type of variable (int/real) and return
            that type.
        
        # TODO: Do better than this... Check stuff first. Try/Catch isn't a great practice
        
        ret = None
        try:
            ret = self.any_int(var)
        except:
            pass
        
        if ret != None:
            return ret
        
        # Intentionally not catching exceptions here
        return self.any_real(var)
    """

    def any_real(self,var,ctx=None):
        """
        Input:
            var == variable name. i.e.: "x"
            (optional) ctx = context if not current one
        Action:
            Resolve possible value for this variable
        Return:
            Discovered variable or None if none found
            Note: this function will cast an Int to a Real implicitly if found
        """
        # Grab appropriate ctx
        ctx = ctx if not None else self.ctx

        # Solve model first
        if not self.isSat():
            logger.debug("any_real: No valid model found")
            # No valid ints
            return None

        # Get model
        m = self.solver.model()

        if self.getZ3Var(var,ctx=ctx) == None:
            logger.debug("any_real: var '{0}' not found".format(var))
            return None
        
        var = self.getZ3Var(var,ctx=ctx)

        # Try getting the value
        value = m.eval(var)

        # Check if we have a known solution
        # Assuming local for now
        if type(value) == z3.ArithRef:
            logger.debug("any_real: var '{0}' not found in solution".format(var))
            # No known solution
            return None

        # Check the type of the value
        if type(value) not in [z3.IntNumRef,z3.RatNumRef]:
            err = "any_real: var '{0}' not of type int or real, of type '{1}'".format(var,type(value))
            logger.error(err)
            raise Exception(err) 

        # Made it! Return it as a real/float
        return float(eval(value.as_string()))


 
    def copy(self):
        """
        Return a copy of the current state
        """

        # Copy the solver state
        solverCopy = z3.Solver()
        solverCopy.add(self.solver.assertions())
        
        return State(
            localVars=deepcopy(self.localVars),
            globalVars=deepcopy(self.globalVars),
            solver=solverCopy,
            ctx=self.ctx,
            functions=self.functions,
            simFunctions=self.simFunctions,
            retVar=self.retVar,
            callStack=deepcopy(self.callStack),
            path=deepcopy(self.path),
            backtrace=deepcopy(self.backtrace),
            retID=copy(self.retID),
            loop=copy(self.loop)
            )
        
