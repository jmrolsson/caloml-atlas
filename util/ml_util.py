import numpy as np  
from sklearn.model_selection import ShuffleSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_curve, auc
import uproot as ur
from keras import utils
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import atlas_mpl_style as ampl
import scipy.ndimage as ndi
ampl.use_atlas_style()

#define a dict for cell meta data
cell_meta = {
    'EMB1': {
        'cell_size_phi': 0.098,
        'cell_size_eta': 0.0031,
        'len_phi': 4,
        'len_eta': 128
    },
    'EMB2': {
        'cell_size_phi': 0.0245,
        'cell_size_eta': 0.025,
        'len_phi': 16,
        'len_eta': 16
    },
    'EMB3': {
        'cell_size_phi': 0.0245,
        'cell_size_eta': 0.05,
        'len_phi': 16,
        'len_eta': 8
    },
    'TileBar0': {
        'cell_size_phi': 0.1,
        'cell_size_eta': 0.1,
        'len_phi': 4,
        'len_eta': 4
    },
    'TileBar1': {
        'cell_size_phi': 0.1,
        'cell_size_eta': 0.1,
        'len_phi': 4,
        'len_eta': 4
    },
    'TileBar2': {
        'cell_size_phi': 0.1,
        'cell_size_eta': 0.2,
        'len_phi': 4,
        'len_eta': 2
    },
}

def createTrainingDatasets(categories, data, cells):
    # create train/validation/test subsets containing 70%/10%/20%
    # of events from each type of pion event
    for p_index, plabel in enumerate(categories):
        splitFrameTVT(data[plabel], trainfrac=0.7)
        data[plabel]['label'] = p_index

    # merge pi0 and pi+ events
    data_merged = pd.concat([data[ptype] for ptype in categories])
    cells_merged = {
        layer: np.concatenate([cells[ptype][layer] for ptype in categories])
        for layer in cell_meta
    }
    labels = utils.to_categorical(data_merged['label'], len(categories))

    return data_merged, cells_merged, labels

def reshapeSeparateCNN(cells):
    reshaped = {
        layer: cells[layer].reshape(cells[layer].shape[0], 1, cell_meta[layer]['len_eta'], cell_meta[layer]['len_phi'])
        for layer in cell_meta
    }

    return reshaped

def setupPionData(inputpath, rootfiles, branches = []):
    # defaultBranches = ['runNumber', 'eventNumber', 'truthE', 'truthPt', 'truthEta', 'truthPhi', 'clusterIndex', 'nCluster', 'clusterE', 'clusterECalib', 'clusterPt', 'clusterEta', 'clusterPhi', 'cluster_nCells', 'cluster_sumCellE', 'cluster_ENG_CALIB_TOT', 'cluster_ENG_CALIB_OUT_T', 'cluster_ENG_CALIB_DEAD_TOT', 'cluster_EM_PROBABILITY', 'cluster_HAD_WEIGHT',
                # 'cluster_OOC_WEIGHT', 'cluster_DM_WEIGHT', 'cluster_CENTER_MAG', 'cluster_FIRST_ENG_DENS', 'cluster_cell_dR_min', 'cluster_cell_dR_max', 'cluster_cell_dEta_min', 'cluster_cell_dEta_max', 'cluster_cell_dPhi_min', 'cluster_cell_dPhi_max', 'cluster_cell_centerCellEta', 'cluster_cell_centerCellPhi', 'cluster_cell_centerCellLayer', 'cluster_cellE_norm']
    defaultBranches = ['clusterIndex', 'truthE', 'nCluster', 'clusterE', 'clusterECalib', 'clusterPt', 'clusterEta', 'clusterPhi', 'cluster_nCells', 'cluster_sumCellE', 'cluster_ENG_CALIB_TOT', 'cluster_ENG_CALIB_OUT_T', 'cluster_ENG_CALIB_DEAD_TOT', 'cluster_EM_PROBABILITY', 'cluster_HAD_WEIGHT', 'cluster_CENTER_MAG', 'cluster_FIRST_ENG_DENS', 'cluster_cellE_norm']

    if len(branches) == 0:
        branches = defaultBranches

    trees = {
        rfile: ur.open(inputpath+rfile+".root")['ClusterTree']
        for rfile in rootfiles
    }
    pdata = {
        ifile: itree.pandas.df(branches, flatten=False)
        for ifile, itree in trees.items()
    }

    return trees, pdata

def splitFrameTVT(frame, trainlabel='train', trainfrac = 0.8, testlabel='test', testfrac = 0.2, vallabel='val'):

    valfrac = 1.0 - trainfrac - testfrac
    
    train_split = ShuffleSplit(n_splits=1, test_size=testfrac + valfrac, random_state=0)
    # advance the generator once with the next function
    train_index, testval_index = next(train_split.split(frame))  

    if valfrac > 0:
        testval_split = ShuffleSplit(
            n_splits=1, test_size=valfrac / (valfrac+testfrac), random_state=0)
        test_index, val_index = next(testval_split.split(testval_index)) 
    else:
        test_index = testval_index
        val_index = []

    frame[trainlabel] = frame.index.isin(train_index)
    frame[testlabel]  = frame.index.isin(test_index)
    frame[vallabel]   = frame.index.isin(val_index)

def setupCells(tree, layer, nrows = -1, flatten=True):
    array = tree.array(layer)
    if nrows > 0:
        array = array[:nrows]
    num_pixels = cell_meta[layer]['len_phi'] * cell_meta[layer]['len_eta']
    if flatten:
        array = array.reshape(len(array), num_pixels)
    
    return array

def standardCells(array, layer, nrows = -1):
    if nrows > 0:
        working_array = array[:nrows]
    else:
        working_array = array

    scaler = StandardScaler()
    if type(layer) == str:
        num_pixels = cell_meta[layer]['len_phi'] * cell_meta[layer]['len_eta']
    elif type(layer) == list:
        num_pixels = 0
        for l in layer:
            num_pixels += cell_meta[l]['len_phi'] * cell_meta[l]['len_eta']
    else:
        print('you should not be here')

    num_clusters = len(working_array)

    flat_array = np.array(working_array.reshape(num_clusters * num_pixels, 1))


    scaled = scaler.fit_transform(flat_array)

    reshaped = scaled.reshape(num_clusters, num_pixels)
    return reshaped, scaler


display_digits = 2

class rocVar:
    def __init__(self,
                 name,  # name of variable as it appears in the root file
                 bins,  # endpoints of bins as a list
                 df,   # dataframe to construct subsets from
                 latex='',  # optional latex to display variable name with
                 vlist=None,  # optional list to append class instance to
                 ):
        self.name = name
        self.bins = bins

        if(latex == ''):
            self.latex = name
        else:
            self.latex = latex

        self.selections = []
        self.labels = []
        for i, point in enumerate(self.bins):
            if(i == 0):
                self.selections.append(df[name] < point)
                self.labels.append(
                    self.latex+'<'+str(round(point, display_digits)))
            else:
                self.selections.append(
                    (df[name] > self.bins[i-1]) & (df[name] < self.bins[i]))
                self.labels.append(str(round(
                    self.bins[i-1], display_digits))+'<'+self.latex+'<'+str(round(point, display_digits)))
                if(i == len(bins)-1):
                    self.selections.append(df[name] > point)
                    self.labels.append(
                        self.latex+'>'+str(round(point, display_digits)))

        if(vlist != None):
            vlist.append(self)


def rocScan(varlist, scan_targets, labels, plotpath, ylabels, data):
    '''
    Creates a set of ROC curve plots by scanning over the specified variables.
    One set is created for each target (neural net score dataset).
    
    varlist: a list of rocVar instances to scan over
    scan_targets: a list of neural net score datasets to use
    labels: a list of target names (strings); must be the same length as scan_targets
    '''
    for target, target_label in zip(scan_targets, labels):
        for v in varlist:
            # prepare matplotlib figure
            plt.cla()
            plt.clf()
            fig = plt.figure()
            fig.patch.set_facecolor('white')
            plt.plot([0, 1], [0, 1], 'k--')

            for binning, label in zip(v.selections, v.labels):
                # first generate ROC curve
                x, y, t = roc_curve(
                    ylabels[data.test & binning][:, 1],
                    target[data.test & binning],
                    drop_intermediate=False,
                )
                var_auc = auc(x, y)
                plt.plot(x, y, label=label+' (area = {:.3f})'.format(var_auc))

            plt.title('ROC Scan of '+target_label+' over '+v.latex)
            plt.xlim(0, 1.1)
            plt.ylim(0, 1.1)
            ampl.set_xlabel('False positive rate')
            ampl.set_ylabel('True positive rate')
            plt.legend()
            plt.savefig(plotpath+'roc_scan_'+target_label+'_'+v.name+'.pdf')
            plt.show()

#rescale our images to a common size
#data should be a dictionary of numpy arrays
#numpy arrays are indexed in cluster, eta, phi
#target should be a tuple of the targeted dimensions
#if layers isn't provided, loop over all the layers in the dict
#otherwise we just go over the ones provided
def rescaleImages(data, target, layers = []):
    if len(layers) == 0:
        layers = data.keys()
    out = {}
    for layer in layers:
        out[layer] = ndi.zoom(data[layer], (1, target[0] / data[layer].shape[1], target[1] / data[layer].shape[2]))

    return out

#just a quick thing to stack things along axis 1, channels = first standard for CNN
def setupChannelImages(data,last=False):
    axis = 1
    if last:
        axis = 3
    return np.stack([data[layer] for layer in data], axis=axis)
