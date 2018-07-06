"""
node.py

Contains the base class for Nodes, and some basic nodes for data analysis.
"""
import copy
from pprint import pprint

import numpy as np

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QWidget

from .data.datadict import DataDict, GridDataDict


__author__ = 'Wolfgang Pfaff'
__license__ = 'MIT'


# Base classes

class NodeBase:
    """
    Base class for all nodes. Manages the basic functionality of sources and
    provides a decorator `@updateOption` for property setters that emits the signal
    `optionsUpdated()`.

    This class is not fully functional -- it must be reimplemented by a QObject
    (in order for signal/slot mechanisms to work)

    Basic idea:
        * `run()` is called when source data or Node options are changed.
          (depending on settings of `updateOnSource` and `updateOnOptionChange`).
          It can also be triggered manually.
        * First, the Node communicates this to its sources (recursively). Once
          all its dependencies have executed their `run()` (in order from top down).
        * If a source's data changes, it broadcasts its new data, and the Node
          updates its reference to the source data.
        * Node will execute `processData` if it determines that its own data is
          not up to date any more (i.e., if sources have changed their data).
        * This will trigger any other Nodes that this Node is a source of to update
          as well (depending on their setting of `updateOnSource`).

    Properties and public attributes:
        updateOnSource : bool
            If True, `run()` is called when source data is updated through
            `setSourceData`.
        updateOnOptionChange : bool
            Flag that can be used to determine whether `run()` should
            be called automatically when options are updated.
            (Signal `optionsUpdated` is only emitted when this is True)
        data : DataDict
            When set, will call `broadcastData`.
        verbose : bool
            If set to True, updates will trigger some output.

    """

    dataProcessed = pyqtSignal(object)
    optionsUpdated = pyqtSignal()
    dataRequested = pyqtSignal()

    sources = ['input']

    def __init__(self, *arg, **kw):
        self.verbose = kw.get('verbose', False)

        self._sources = {}
        self._updateOnSource = True
        self._uptodate = False
        self._data = None
        self._updateOnOptionChange = True
        self._running = False
        self._grid = False

        self._sources = { s : {'ref' : None, 'data' : None} \
            for s in self.__class__.sources }

        self.optionsUpdated.connect(self.run)

        for k, v in self._sources.items():
            setattr(self, 'set' + k.capitalize(),
                lambda ref: self.setSource(k, ref))
            setattr(self, 'set' + k.capitalize() + 'Data',
                pyqtSlot(object)(lambda data: self.setSourceData(k, data)))
            setattr(self, 'get' + k.capitalize() + 'Data',
                lambda: self._sources[k]['data'])

    @staticmethod
    def asGrid(data, names=None, makeCopy=True):
        if isinstance(data, GridDataDict):
            if makeCopy:
                data = copy.copy(data)

            if names is not None:
                remove = []
                for n, v in data.items():
                    if n not in names and n in data.dependents():
                        remove.append(n)
                for r in remove:
                    del data[r]
                data.remove_unused_axes()
                data.validate()

                return data

        elif isinstance(data, DataDict):
            griddata = data.get_grid(names)
            griddata.validate()
            return griddata

        else:
            raise ValueError("Data has unrecognized type.")


    @staticmethod
    def updateOption(func):
        def wrap(self, val):
            ret = func(self, val)
            self._uptodate = False
            if self._updateOnOptionChange:
                self.optionsUpdated.emit()
            return ret
        return wrap

    @property
    def updateOnSource(self):
        return self._updateOnSource

    @updateOnSource.setter
    def updateOnSource(self, val):
        self._updateOnSource = val

    @property
    def updateOnOptionChange(self):
        return self._updateOnOptionChange

    @updateOnOptionChange.setter
    def updateOnOptionChange(self, val):
        self._updateOnOptionChange = val

    @property
    def grid(self):
        return self._grid

    @grid.setter
    @NodeBase.updateOption
    def grid(self, val):
        self._grid = val

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, val):
        if val is None:
            val = {}
        self._data = val
        self.broadcastData()

    @pyqtSlot()
    def broadcastData(self):
        self.dataProcessed.emit(self._data)

    def setSourceData(self, sourceName, value):
        """
        Sets the internally referenced data of source `sourceName` to `value`.
        `sourceName` must be defined in the class variable `sources`
        at class definition.

        If the `updateOnSource` property is True, will call `run()`.
        """
        if sourceName not in self._sources:
            raise ValueError("'{}' is not a recognized source.")

        if self.verbose:
            print(self, 'data set from', sourceName)

        self._sources[sourceName]['data'] = value
        self._uptodate = False
        if self._updateOnSource:
            self.run()

    def setSource(self, sourceName, ref):
        """
        Sets the reference to source `sourceName` to `ref`.
        `sourceName` must be defined in the class variable `sources`
        at class definition.

        Will connect the `dataProcessed` signal of the source to setting the
        corresponding data value in this instance, and connect this instance's
        `dataRequested` signal to the sources `broadcastData` method.
        Will emit the `dataRequested` signal at the end.
        """
        if sourceName not in self._sources:
            raise ValueError("'{}' is not a recognized source." )

        setfunc = getattr(self, 'set' + sourceName.capitalize() + 'Data')
        src = self._sources[sourceName]['ref']
        if src is not None:
            src.dataProcessed.disconnect(setfunc)
            self.dataRequested.disconnect(src.broadcastData)

        self._sources[sourceName]['ref'] = ref
        src = self._sources[sourceName]['ref']
        src.dataProcessed.connect(setfunc)
        self.dataRequested.connect(src.broadcastData)
        self.dataRequested.emit()

    @pyqtSlot()
    def run(self):
        """
        Calls `run()` on all sources. During this, any `dataProcessed` signals
        from the sources will be ignored. After that, call our own
        `processData` if an update is required.
        """
        if not self._running:
            self._running = True
            for n, s in self._sources.items():
                if s['ref'] is not None:
                    s['ref'].run()

            if not self._uptodate:
                self.data = self.processData()
                if self.verbose:
                    print('processed data:', self)
                    pprint(self.data)
                    print('')
                self._uptodate = True
                self._running = False
        else:
            self._uptodate = False

    def processData(self):
        raise NotImplementedError


class Node(QObject, NodeBase):
    """
    Base class for a widget-less Node.

    This base class has a trivial implementation of `processData`. Children
    need to implement their own functionality only in this method.
    """

    def processData(self):
        """
        Returns its interally stored data.
        """
        return self.data


class NodeWidget(QWidget, NodeBase):
    """
    Base class for a node that's based on a Widget.
    """

    def __init__(self, parent=None, **kw):
        super().__init__(parent=parent, **kw)


# Elementary data processing nodes

class DataSelector(Node):
    # TODO: it should be possible to select multiple names, as long as they're
    #       compatible in some way. probably should just mean same dependencies?

    def __init__(self, *arg, **kw):
        super().__init__(*arg, **kw)

        self._grid = True
        self._dataName = None
        self._slices = {}
        self._axesOrder = {}
        self._squeeze = True

    @property
    def dataName(self):
        return self._dataName

    @dataName.setter
    @Node.updateOption
    def dataName(self, val):
        self._dataName = val

    @property
    def slices(self):
        return self._slices

    @slices.setter
    @Node.updateOption
    def slices(self, val):
        self._slices = val

    @property
    def axesOrder(self):
        return self._axesOrder

    @axesOrder.setter
    @Node.updateOption
    def axesOrder(self, val):
        self._axesOrder = val

    @property
    def squeeze(self):
        return self._squeeze

    @squeeze.setter
    @Node.updateOption
    def squeeze(self, val):
        self._squeeze = val


    @staticmethod
    def axesList(data, dataName=None):
        lst = []
        if dataName is None:
            for k, v in data.items():
                if 'axes' in v:
                    for n in v['axes']:
                        if n not in lst:
                            lst.append(n)
        else:
            if dataName in data and 'axes' in data[dataName]:
                lst = data[dataName]['axes']

        return lst

    def validate(self, data):
        return True

    def processData(self):
        data = self.getInputData()

        if data is None:
            return {}

        if not self.validate(data):
            return {}

        if self.dataName is None:
            return {}

        if hasattr(data, 'get_grid') and self._grid:
            data = data.get_grid(self.dataName)
        else:
            _data = {self.dataName : data[self.dataName]}
            for k, v in data:
                if k in data[self.dataName].get('axes', []):
                    _data[k] = v
            data = _data

        if self.grid:
            _datavals = data[self.dataName]['values']
            _axnames = data[self.dataName]['axes']

            slices = [np.s_[::] for a in _axnames]
            for n, s in self.slices.items():
                idx = _axnames.index(n)
                slices[idx] = s
                data[n]['values'] = data[n]['values'][s]
            data[self.dataName]['values'] = _datavals[slices]
            _datavals = data[self.dataName]['values']

            neworder = [None for a in _axnames]
            oldorder = list(range(len(_axnames)))
            for n, newidx in self.axesOrder.items():
                neworder[newidx] = _axnames.index(n)

            for i in neworder:
                if i in oldorder:
                    del oldorder[oldorder.index(i)]

            for i in range(len(neworder)):
                if neworder[i] is None:
                    neworder[i] = oldorder[0]
                    del oldorder[0]

            data[self.dataName]['values'] = _datavals.transpose(tuple(neworder))
            _datavals = data[self.dataName]['values']
            data[self.dataName]['axes'] = [_axnames[i] for i in neworder]
            _axnames = data[self.dataName]['axes']

            if self.squeeze:
                oldshape = _datavals.shape
                data[self.dataName]['values'] = np.squeeze(_datavals)
                for i, n in enumerate(_axnames):
                    if oldshape[i] < 2:
                        del data[self.dataName]['axes'][i]
                        del data[n]

        return data