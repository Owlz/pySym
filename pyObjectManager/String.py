import z3
import ast
import logging
from pyObjectManager.Int import Int
from pyObjectManager.Real import Real
from pyObjectManager.BitVec import BitVec
from pyObjectManager.List import List
from pyObjectManager.Char import Char
import pyState

logger = logging.getLogger("ObjectManager:String")

class String:
    """
    Define a String
    """

    def __init__(self,varName,ctx,count=None,string=None,variables=None,state=None):
        assert type(varName) is str
        assert type(ctx) is int
        assert type(count) in [int, type(None)]

        self.count = 0 if count is None else count
        self.varName = varName
        self.ctx = ctx
        # Treating string as a list of BitVecs
        self.variables = [] if variables is None else variables

        if string is not None:
            self.setTo(string)

        if state is not None:
            self.setState(state)


    def copy(self):
        return String(
            varName = self.varName,
            ctx = self.ctx,
            count = self.count,
            variables = [x.copy() for x in self.variables],
            state = self.state if hasattr(self,"state") else None
        )

    def __deepcopy__(self,blerg):
        return self.copy()


    def setState(self,state):
        """
        This is a bit strange, but State won't copy correctly due to Z3, so I need to bypass this a bit by setting State each time I copy
        """
        assert type(state) == pyState.State

        self.state = state
        for var in self.variables:
            var.setState(state)

    def increment(self):
        self.count += 1
        # reset variable list if we're incrementing our count
        self.variables = []
    
    def setTo(self,var):
        """
        Sets this String object to be equal/copy of another. Type can be str or String.
        Remember that this doesn't set anything in Z3
        """
        assert type(var) in [String, str]
        
        # For now, just add as many characters as there was originally
        for c in var:
            # Assuming 8-bit BitVec for now
            # TODO: Figure out a better way to handle this... Characters might be of various bitlength... Some asian encodings are up to 4 bytes...
            #self.variables.append(BitVec('{2}{0}[{1}]'.format(self.varName,len(self.variables),self.count),ctx=self.ctx,size=16))
            self.variables.append(Char('{2}{0}[{1}]'.format(self.varName,len(self.variables),self.count),ctx=self.ctx))


    def _isSame(self,**args):
        """
        Checks if variables for this object are the same as those entered.
        Assumes checks of type will be done prior to calling.
        """
        return True

    def index(self,elm):
        """
        Returns index of the given element. Raises exception if it's not found
        """
        return self.variables.index(elm)

    def __getitem__(self,index):
        """
        We want to be able to do "string[x]", so we define this.
        """
        if type(index) is slice:
            # TODO: Redo this to return as string object
            # Build a new List object containing the sliced stuff
            newList = String("temp",ctx=self.ctx)
            oldList = self.variables[index]
            for var in oldList:
                newList.append(var)
            return newList
            

        return self.variables[index]

    def __setitem__(self,key,value):
        """
        String doesn't support setitem
        """
        err = "String type does not support item assignment"
        logger.error(err)
        raise Exception(err)


    def length(self):
        return len(self.variables)

    def pop(self,index):
        """
        Not exactly something you can do on a string, but helpful for our symbolic execution
        """
        return self.variables.pop(index)
