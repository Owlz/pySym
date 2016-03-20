import z3
import ast
import logging
from copy import deepcopy
#from pyState import z3Helpers
from pyObjectManager.Int import Int
from pyObjectManager.Real import Real
from pyObjectManager.BitVec import BitVec


logger = logging.getLogger("ObjectManager")

CTX_GLOBAL = 0
CTX_RETURNS = 1

class ObjectManager:
    """
    Object Manager will keep track of objects. Generally, Objects will be variables such as ints, lists, strings, etc.
    """

    """
    variables = {
        <ctx> : {
            <varName> : <var Class Instance>
        }
    }
    """

    def __init__(self,variables=None):
        self.variables = {CTX_GLOBAL: {}, CTX_RETURNS: {}} if variables is None else variables

    def newCtx(self,ctx):
        """
        Sets up a new context (ctx)
        """
        assert ctx is not None

        self.variables[ctx] = {}


    def resolveVariable(self,obj,ctx):
        """
        Input:
            obj = ast object to resolve
            ctx = Context for this variable
        Action: 
           Resolve it to an object z3 can work with
        Return:
            Resolved z3 object
        """
        # List of object we current understand
        assert type(obj) in [ast.Name]
        
        # Basically copying this function over for now. Will modify later.
        return self.getZ3Var(obj.id,ctx=ctx)


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


    def getVar(self,varName,ctx,varType=None,kwargs=None):
        """
        Input:
            varName = name of variable to get
            ctx = Context for variable
            (optional) varType = Class type of variable (ex: pyObjectManager.Int)
            (optional) kwargs = args needed to instantiate variable
        Action:
            Find appropriate variable object, creating one if necessary
        Returns:
            pyObjectManager object for given variable (i.e.: pyObjectManager.Int)
        """
        
        # Attempt to return variable
        assert type(varName) is str
        assert type(ctx) is int
        assert varType in [None, Int, Real, BitVec]
        
        create = False
        
        # Check that we already have this variable defined
        if varName in self.variables[ctx]:
            
            # Check the type of the var is correct
            if varType is not None:

                # If the variable type is different or it's settings are different, we need to create a new object
                if type(self.variables[ctx][varName]) is not varType or not self.variables[ctx][varName]._isSame(**kwargs if kwargs is not None else {}):
                    create = True
            
            # If we can just return the current one, let's do it
            if not create:
                return self.variables[ctx][varName]

        # Looks like we need to create a var
        if varType == None:
            err = "getVar: Need to create '{0}' but no type information given".format(varName)
            logger.error(err)
            raise Exception(err)
        
        # Make the var
        self.variables[ctx][varName] = varType(varName=varName,ctx=ctx,**kwargs if kwargs is not None else {})
        
        return self.variables[ctx][varName]


    def copy(self):
        """
        Return a copy of the Object Manager
        """

        return ObjectManager(
            variables = deepcopy(self.variables)
        )

