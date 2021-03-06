"""

A set of base classes to abstract away loading data.

"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import six
import inspect
from six.moves import cPickle as pickle

from six import with_metaclass
from abc import ABCMeta, abstractmethod, abstractproperty
from .utils import all_subclasses as _all_subclasses
from functools import wraps
import numpy as np


class RequireActive(Exception):
    """
    Exception sub-class to be raised when a function which
    requires the handler to be active is called on an inactive
    handler
    """
    pass


class RequireInactive(Exception):
    """
    Exception sub-class to be raised when a function which
    requires the handler to be inactive is called on an active
    handler
    """
    pass


def available_handler_list(base_handler, filter_list=None):
    """
    Returns a list of handlers which are sub-classes of `base_handler`.

    The list is then filtered to include only classes which are sub-classes
    of any of the classes in `filter_list.

    The thought is to use this something like

    >>> d_sinks = available_handler_list(DistributionSink)

    returns a list of all of the distribution sink handlers and
    >>> from base_file_handlers import FileHandler
    >>> d_file_sinks = available_handler_list(DistributionSink, [FileHandler,])

    Parameters
    ----------
    base_handler : type
        The base-class to find sub-classes of

    filter_list : list of type
        Only return handlers which are a subclass of any of the
        elements in filter_list (OR logic).
    """
    # grab the sub-classes
    h_lst = []
    # if base class is not abstract, keep it too
    if not inspect.isabstract(base_handler):
        h_lst.append(base_handler)
    # yay recursion
    _all_subclasses(base_handler, h_lst)
    # list comprehension logic
    return [h for h in h_lst if filter_list is None or
            any(issubclass(h, filt) for filt in filter_list)]


class BaseDataHandler(with_metaclass(ABCMeta, object)):
    """
    An ABC for all data source and sink objects.

    This exists because the minimal required functions for
    both source and sink are the same.

    In both cases the `__init__` function should capture enough
    information to set up the sourcing/sinking of data, but not
    preform any initialization until `activate` is called.  This is
    to allow complex handlers to be shipped via pickle over the network
    (ex ipython parallel on remote machines) or via command line arguments
    for scripts (ex current pyLight frame work or cluster scheduling system).

    The consumers of these objects should take care of calling
    `activate` and `deactivate`.

    Ideally, this will be the last object in the MRO chain, put last when using
    multiple inheritance.
    """
    @classmethod
    def available(cls):
        """
        Return if this handler is available for use.  This is to smooth
        over import and configuration issues.  Sub-classes should over-ride
        this function, by default the handlers are assumed to be usable if
        they are imported.

        Returns
        -------
        available : bool
            If the handler class is able to be used.
        """
        return True

    @classmethod
    def id(cls):
        return cls.__name__.lower()

    def __init__(self, *args, **kwargs):
        # this should always be last, but if the order is
        # flipped on the def, pass up the MRO chain.
        # if this is last and all kwargs have not been exhausted,
        # then object will raise an error
        super(BaseDataHandler, self).__init__(*args, **kwargs)
        self._active = False

    def activate(self):
        """
        Sub-classes should extend this to set handler up to source/sink
        data. This may be a no-op or it may involve opening files/network
        connections. Basically deferred initialization.
        """
        self._active = True

    def deactivate(self):
        """
        Sub-classes will need to extend this method to tear down any
        non-picklable structures (ex, open files)
        """

        self._active = False

    @property
    def active(self):
        """
        If the handler is active

        Returns
        -------
        active : bool
            If the source/sink is 'active'
        """

        return self._active

    @abstractproperty
    def kwarg_dict(self):
        """
        `dict` to reconstruct

        This should return enough information to passed to
        cls.__init__(**obj.kwarg_dict) and get back a functionally
        identical version of the object.
        """
        return dict()

    def __getstate__(self):
        """
        Return kwarg_dict dict

        Part of over-riding default pickle/unpickle behavior

        Raise exception if trying to pickle and active handler
        """
        if self.active:
            raise pickle.PicklingError("can not pickle active handler")
        return self.kwarg_dict

    def __setstate__(self, in_dict):
        """
        Over ride the default __setstate__ behavior and force __init__
        to be called
        """
        self.__init__(**in_dict)

    def __enter__(self):
        """
        Set up a context manager and activate the handler
        """
        self.activate()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Clean up the context manager and deactivate the handler
        """
        self.deactivate()


def require_active(fun):
    """
    A decorator to use on functions which require the handler to
    be active
    """
    @wraps(fun)
    def inner(self, *args, **kwargs):
        if not self.active:
            raise RequireActive("Handler must be active")
        return fun(self, *args, **kwargs)

    return inner


def require_inactive(fun):
    """
    A decorator to use on functions which require the handler to
    be active
    """
    @wraps(fun)
    def inner(self, *args, **kwargs):
        if self.active:
            raise RequireInactive("Handler must be inactive")
        return fun(self, *args, **kwargs)

    return inner


class BaseSource(BaseDataHandler):
    """
    An ABC for all data source classes.

    This layer exists so that the `isinstace(obj, BaseSource)` will
    work.
    """
    pass


class BaseSink(BaseDataHandler):
    """
    An ABC for all data sing classes.

    This layer exists so that the `isinstace(obj, BaseSink)` will
    work.
    """
    @abstractmethod
    def make_source(self, source_klass=None):
        """
        Returns a source object which will access the data written
        into this sink object.  The optional kwarg `source_klass`
        provides a hint as to what type of source to create (this
        will be relevant/useful with we end up with sources that
        step through the same data in different ways (exposures vs
        sinograms) or maybe not)

        Parameters
        ----------
        source_klass : None or type
            if not-None, what class to use to build the source object
        """
        pass


class DistributionSource(BaseSource):
    """
    An ABC to specify the interface for reading in distributions.

    Distributions are an output data type which are assumed to have two
    sets of values, `bin_edges` and `bin_values`.  Bin edges is assumed to
    be monotonic and increasing.

    `bin_edges` can be the same length as `bin_values`, denoting the left edges
    of the bins or one element longer with the last element marking the right
    edge of the last bin.
    """
    @abstractmethod
    def values(self):
        """
        Return the `bin_values` as an array-like object

        Returns
        -------
        bin_values : np.ndarray like
            The value of the bins
        """
        pass

    @abstractmethod
    def bin_edges(self, include_right=False):
        """
        Return the `bin_edges` as an array-like object

        Parameters
        ----------
        include_right : bool, optional
            if True, then return the right edge of the last bin as the
            last element

        Returns
        -------
        bin_edges : np.ndarray like
            The location of the bin edges
        """
        pass

    @abstractmethod
    def bin_centers(self):
        """
        Return the centers of the bins

        Returns
        -------
        bin_centers : np.ndarray like
            The centers of the bins
        """
        pass


class FrameSource(BaseSource):
    """
    An ABC for the interface to read in images

    Images are N-D arrays of any type.

    All handlers are assumed to wrap a sequence of images, but may be
    length 1.

    The first pass will only have a single access function
    'get_frame` which will return what ever the natural 'frame'
    is.  More specific sub-classes should provide a way to more
    sensibly slice volumes (ex iterate over sinograms or projections).

    Still up in the air on if we want to do this with a few class
    with lots of functions or many classes with a few functions.
    Leaning toward lots of simple classes
    """
    def __init__(self, resolution=None, resolution_units=None,
                *args, **kwargs):
        """
        Parameters
        ----------
        resolution : scalar, iterable, None
            axial resolution, scalar, iterable converted to np.ndarray
            if iterable, length should match underlying dimension
            if None, defaults to 1

        resolution_units : str or None
            units of axial dimensions.  If None, defaults to 'pix'
        """
        # deal with default values
        if resolution is None:
            resolution = 1

        if resolution_units is None:
            resolution_units = 'pix'

        # save values
        self._resolution = np.array(resolution)
        self._resolution_units = resolution_units
        # pass up the mro stack
        super(FrameSource, self).__init__(*args, **kwargs)

    @property
    def resolution(self):
        """
        The axial size of a voxel as a numpy array, if isotropic, 0d,
        else dimension should match the dimension returned by get_frame.
        Units given by `resolution_units`.

        Returns
        -------
        resolution : np.ndarray
           The axial size of a voxel
        """
        return self._resolution

    @property
    def resolution_units(self):
        """
        The units for the `resolution` as a string.  This may be changed
        to be some clever unit-tracking class.

        Returns
        -------
        resoultion_units : str
            Units of the resolution
        """
        return self._resolution_units

    @abstractmethod
    def get_frame(self, frame_num):
        """
        Returns what ever the sub-class thinks is 'frame'.

        Parameters
        ----------
        frame_num : uint
            The frame to extract
        """
        pass

    def get_frame_metadata(self, frame_num, key):
        """
        Returns meta-data for frame `frame_num`.  This is frame-specific
        meta-data (like exact timestamp).

        If the key is not found, raises `KeyError`.  This is different
        than how traitslets behave. The logic to raise instead of
        returning `None` is to make it possible
        to check if a metadata value has been defined.

        The base implementation always raises.  Sub-classes should only
        call up the mro stack _after_ failing to find the key in their
        own internals

        Parameters
        ----------
        frame_num : uint
            The frame to extract

        key : str
            The meta-data key to extract
        """
        raise KeyError()

    def get_metadata(self, key):
        """
        Returns meta-data for the set of frames (this is 'global' meta-data
        like the name of the instrument).

        If the key is not found, raises `KeyError`.  This is different
        than how traitslets behave. The logic to raise instead of
        returning `None` is to make it possible
        to check if a metadata value has been defined.

        The base implementation always raises.  Sub-classes should only
        call up the mro stack _after_ failing to find the key in their
        own internals

        Parameters
        ----------
        key : str
            The meta-data key to extract
        """
        raise KeyError()

    @abstractmethod
    def __len__(self):
        """
        Length is obligatory.
        """
        pass

    def __getitem__(self, arg):
        """
        Defining __getitem__ is mandatory so that source[j] works
        """
        # TODO sort out if we want to steal the pims code here
        return self.get_frame(arg)

    def __iter__(self):
        """
        Defining __iter__ so source is iterable is mandatory
        """
        raise NotImplementedError()

    @property
    def kwarg_dict(self):
        dd = super(FrameSource, self).kwarg_dict
        dd.update({'resolution': self.resolution,
                    'resolution_units': self.resolution_units})
        return dd


class FrameSink(BaseSink):
    """
    An ABC for sinking frames and frame sequences
    """
    def __init__(self, resolution=None, resolution_units=None,
                    *args, **kwargs):
        """
        Parameters
        ----------
        resolution : scalar, iterable, None
            axial resolution, scalar, iterable converted to np.ndarray
            if iterable, length should match underlying dimension
            if None, defaults to 1

        resolution_units : str or None
            units of axial dimensions.  If None, defaults to 'pix'
        """
        # deal with default values
        if resolution is None:
            resolution = 1

        if resolution_units is None:
            resolution_units = 'pix'

        # save values
        self._resolution = np.array(resolution)
        self._resolution_units = resolution_units
        # pass up the mro stack
        super(FrameSink, self).__init__(*args, **kwargs)

    def set_resolution(self, resolution, resolution_units):
        # TODO add some error checking
        self._resolution = resolution
        self._resolution_units = resolution_units

    @property
    def resolution(self):
        return self._resolution

    @property
    def resolution_units(self):
        return self._resolution_units

    @abstractmethod
    def record_frame(self, img, frame_number, frame_md):
        """
        Record a frame to the sink

        Parameters
        ----------
        img : ndarray
            a frame, dimensional will depend on the implementation

        frame_number : uint
           The frame number

        frame_md : dict, md_dict, or None
            frame-level meta-data
        """
        pass

    #@abstractmethod
    ## def record_frame_sequence(self, imgs,
    ##                         frame_numbers_list=None,
    ##                         frame_md_list=None):
    ##     """
    ##     Record a sequence of frames to the sink
    ##     """
    ##     raise NotImplementedError("this will be come an abstract method eventually") # noqa

    @abstractmethod
    def set_metadata(self, md_dict):
        """
        Set 'global' level metadata about all of the frames being put
        into this sink

        Parameters
        ----------
        md_dict : md_dict or dict
            The meta-data to set
        """
        pass

    @property
    def kwarg_dict(self):
        dd = super(FrameSink, self).kwarg_dict
        dd.update({'resolution': self.resolution,
                    'resolution_units': self.resolution_units})
        return dd


class ImageSink(FrameSink):
    """
    Classes where `record_*` expects 2D arrays (images/slices/planes)
    """
    pass


class ImageSource(FrameSource):
    """
    Classes where `get_frame` returns 2D arrays (images/slices/planes)
    """
    pass


class RawTomoData(ImageSource):
    """
    Class for representing raw tomographic data
    """
    @abstractmethod
    def iter_by_sinogram(self):
        """
        Return sinograms (\theta, x) as a function of y

        Returns
        -------
        by_sino : generator
            Yields sinograms to get y-value enumerate and use
            resolution to covert voxel -> real units
        """
        pass

    @abstractmethod
    def iter_by_projection(self):
        """
        Iterate by projection.

        Returns
        -------
        by_proj : generator
            Yields projects.  To get angle values enumerate and
            convert to deg/rad via resolution values.
        """
        pass


class VolumeSource(FrameSource):
    """
    Classes where `get_frame` returns 3D arrays (volume)
    """
    pass


class SpecturmSource(FrameSource):
    """
    Hypothetical classes that return arrays of spectra.
    """
    pass


class DistributionSink(BaseSink):
    """
    An ABC for specifying the interface for writing distributions.

    See DistributionSource for more.
    """
    @abstractmethod
    def write_dist(self, bins, vals, right_edge=False):
        """
        Sink the bin edges and values.

        Parameters
        ----------
        bins : iterable
           bin edges

        vals : iterable
           bin values

        right_edge : bool, optional
           if True, include the right edge of the last bin in the data.
        """
        pass


class TableSink(BaseSink):
    """
    An ABC for sequences of tables
    """
    @abstractmethod
    def write_table(self, rec_array, table_name):
        """
        Sink a table from a record array/numpy array with
        compound data types

        Parameters
        ----------
        rec_array : ndarray/recarray
            The table data to be sunk

        table_name : str
            Name of the table
        """
        pass


class TableSource(BaseSource):
    """
    An ABC for sequences of tables
    """
    @abstractmethod
    def read_table(self, table_name):
        """
        Source a table

        Parameters
        ----------
        table_name : str
            The name of the table to be retrieve

        Returns
        -------
        rec_array : ndarray with compound datatype
            The returned data
        """
        pass

    @require_active
    def iter_tables(self):
        """
        Iterate through all tables in source

        Returns
        -------
        gen : generator
           Generator which yields ndarrays with
           compound data types
        """
        keys = self.table_keys()
        for k in keys:
            yield self.read_table(k)

    @abstractmethod
    def table_keys(self):
        """
        Return an iterable of the tables in this source

        Returns
        -------
        keys : iterable
           iterable of strings which are the table names
        """
        pass
