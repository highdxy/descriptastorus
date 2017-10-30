from __future__ import print_function
from . import raw
from . import MolFileIndex
import os, sys, contextlib, pickle
import logging

try:
    from .descriptors import MakeGenerator
except:
    MakeGenerator = None
    logging.error("Unable to make new descriptors, descriptor generator not installed")

try:
    import kyotocabinet
except ImportError:
    kyotocabinet = None

from .raw import Mode

class DescriptaStoreIter:
    def __init__(self, store):
        self.store = store
        self.i = -1
    def next(self):
        self.i += 1
        if self.i == len(self.store):
            raise StopIteration()

        try:
            return self.store.index.get(self.i), self.store.getDescriptors(self.i)
        except:
            print("== DescriptaStoreIter Failed at index", self.i)
            raise
    
class DescriptaStore:
    def __init__(self, dbdir, mode=Mode.READONLY):
        """dbdir -> opens a descriptor storage
         
        >>> store = DescriptaStore(db)
        >>> len(store)

        # access the options used to create this store
        #  (this is optional and may not exist)
        >>> store.options
        ...
        
        Iterate through molecule data ([moldata, <optional name>], descriptors)
        >>> for moldata, descriptors in store:
        >>>     pass

        Iterate through only the descriptors
        >>> for i,prop in enumerate(store.descriptors()):
        >>>    pass

        If name indexed:
        >>> row = store.lookupName("ZWIMER-03065")
        
        If inchi key index:
        Since inchi keys may collide, this can return multiple indices
        >>>  rows = store.lookupInchiKey("BCWYEXBNOWJQJV-UHFFFAOYSA-N")
        """
        self.desctiporDB = dbdir
        self.db = raw.RawStore(dbdir, mode=mode)
        self.index = MolFileIndex.MolFileIndex(os.path.join(dbdir, "__molindex__"))

        inchi = os.path.join(dbdir, "inchikey.kch")
        if os.path.exists(inchi):
            if not kyotocabinet:
                print("Inchi lookup exists, but kyotocabinet is not installed.",
                      file=sys.stderr)
            else:
                self.inchikey = kyotocabinet.DB()
                if mode == Mode.READONLY:
                    self.inchikey.open(inchi, kyotocabinet.DB.OREADER)
                else:
                    self.inchikey.open(inchi, kyotocabinet.DB.OWRITER)

        else:
            self.inchikey = None

        name = os.path.join(dbdir, "name.kch")
        if os.path.exists(name):
            if not kyotocabinet:
                logging.warning("Name lookup exists, but kyotocabinet is not installed.")
                self.name = None
            else:
                self.name = kyotocabinet.DB()
                if mode == Mode.READONLY:
                    self.name.open(name, kyotocabinet.DB.OREADER)
                else:
                    self.name.open(name, kyotocabinet.DB.OWRITER)
        else:
            print("Couldn't open name db", name, file=sys.stderr)
            self.name = None

        self.options = None
        optionsfile = os.path.join(dbdir, "__options__")
        if os.path.exists(optionsfile):
            with open(optionsfile, 'rb') as f:
                self.options = pickle.load(f)

        # index the calculated flags
        datacols = [(i,name) for i,name in enumerate(self.db.colnames) if "_calculated" not in name]
        self.datanames = [name for i,name in datacols]
        self.dataindices = [i for i,name in datacols]
        

    def close(self):
        self.db.close()
        self.index.close()
        if self.inchikey is not None:
            self.inchikey.close()
        
        if self.name is not None:
            self.name.close()
            
    def __len__(self):
        return self.db.N

    def __iter__(self):
        return DescriptaStoreIter(self)

    def getDescriptorCalculator(self):
        """Returns the descriptor calculator (if possible) for the store
        In general this requires the same run-time environment as the 
        storage, so this might not be possible"""
        try:
            return MakeGenerator(self.options['descriptors'].split(","))
        except:
            logging.exception("Unable to make generator from store")
            return None

    def getDescriptorNames(self, keepCalculatedFlags=False):
        """keepCalculatedFlags=False -> return the descriptor names for the store
        if keepCalculatedFlags is True return the boolean flags that indicate
        if results were calculated for the descriptor subset.
        """
        if keepCalculatedFlags:
            return self.db.colnames[:]
        return self.datanames
        
    def getDescriptors(self, index, keepCalculatedFlags=False):
        """index, keepCalculatedFlags=False -> return the descriptors at index
        if keepCalculatedFlags is True return the boolean flags that indicate
        if results were calculated for the descriptor subset.
        """
        
        v = self.db.get(index)
        if keepCalculatedFlags:
            return v
        else:
            return [v[i] for i in self.dataindices]
        
    def getDescriptorsAsDict(self, index):
        """index -> return the descriptors as an index"""
        return self.db.getDict(index)
    
    def descriptors(self):
        """Returns the raw storage for the descriptors"""
        return self.db

    def molIndex(self):
        """Returns the mol index"""
        return self.index

    def lookupName(self, name):
        """name -> returns the index of the given name"""
        if self.name is None:
            try:
                logging.warning("Using slower memory intensive option")
                logging.warning("Loading names...")
                self.name = {name:i for i, (moldata, name)
                             in enumerate(self.index)}
                logging.warning("...done loading")
            except:
                logging.exception("Names not available from original input")
                raise ValueError("Name index not available")

        try:
            row = int(self.name[name])
        except:
            logging.exception("whups")
            raise IndexError("Name %r not found"%name)
        
        return row
    
    def lookupInchiKey(self, key):
        """key -> returns the indicies of the inchi key"""
        if self.inchikey is None:
            raise ValueError("Inchi index not available")
        strres = self.inchikey[key]
        if strres is None:
            raise KeyError(key)
        res =  eval(strres)
        return res
    
