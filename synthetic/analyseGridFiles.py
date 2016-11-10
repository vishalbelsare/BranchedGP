from matplotlib import pyplot as plt
from BranchedGP import VBHelperFunctions as v
import pickle
import glob
import numpy as np


if __name__ == "__main__":
    # Control settings
    #     strDataDir = 'data'  # Where data files reside
    strDataDir = '/home/mqbssaby/transfer/syn'
    fPlotAllFits = False
    fPlotBestFit = False
    fSparse = False
    # Collections across all samples
    BtryAll = None
    BgridSearchAll = None
    objAll = None
    errorInBranchingPtAll = None
    logLikelihoodRatioAll = None
    timingInfoAll = None
    # iterate over all files and make list of all results - so code between jug and here same
    rallDescr = ['Full', 'Sparse']
    fullNamel = ['%s/runArrayJob_%s' % (strDataDir, rallDescr[0]),
                 '%s/runArrayJob_%s' % (strDataDir, rallDescr[1])]
    rall = list()
    for fullName in fullNamel:
        rFullOrSparse = list()
        for file in glob.glob("%s*.p" % fullName):
            print('processing file %s' % file)
            r = pickle.load(open(file, "rb"))
            # get seed
            seed = int(file[len(fullName):-2])
            r['seed'] = seed  # add seed
            rFullOrSparse.append(r)
        rall.append(rFullOrSparse)
    # Common code for Jug and grid
    plt.close('all')
    plt.ion()
    for ir, res in enumerate(rall):
        for ns, r in enumerate(res):  # get task
            '''{'errorInBranchingPt': errorInBranchingPt,
              'logLikelihoodRatio': logLikelihoodRatio,
              'Btry': Btry, 'BgridSearch': BgridSearch,
              'mlist': mlist, 'timingInfo': timingInfo} '''
            BgridSearch = r['BgridSearch']
            Btry = r['Btry']
            if(BtryAll is None):
                # First run
                BtryAll = Btry
                BgridSearchAll = BgridSearch
                objAll = np.zeros((len(Btry), len(BgridSearch), len(res)))  # trueB X cand B X nSamples
                objIntAll = np.zeros((len(Btry), len(res)))  # trueB X nSamples
                errorInBranchingPtAll = np.zeros((len(Btry), len(res)))  # trueB X nSamples
                logLikelihoodRatioAll = np.zeros((len(Btry), len(res)))  # trueB X nSamples
                timingInfoAll = np.zeros((len(rall), len(Btry), len(BgridSearch), len(res)))
                objAll[:] = np.nan
                errorInBranchingPtAll[:] = np.nan
                logLikelihoodRatioAll[:] = np.nan
                timingInfoAll[:] = np.nan
            else:
                assert np.all(BgridSearchAll == BgridSearch)
                assert len(BtryAll) == len(Btry)  # cannot test nan equality
            # Update collection for this sample
            errorInBranchingPtAll[:, ns] = r['errorInBranchingPt']
            logLikelihoodRatioAll[:, ns] = r['logLikelihoodRatio']
            timingInfoAll[ir, :, :, ns] = r['timingInfo']
            mlist = r['mlist']
            assert len(mlist) == len(Btry), 'list size is %g - should be %g' % (len(mlist), len(Btry))
            for iml, ml in enumerate(mlist):
                # Experiment for given B, we have one fit per search grid B
                ''' {'trueBStr': bs, 'bTrue': bTrue,
                      'pt': m.t, 'Y': m.Y.value, 'mlocallist': mlocallist}) '''
                mlocall = ml['mlocallist']
                if(len(mlocall) == 0):
                    print('sample %g seed %g %s %s failed' % (ns, r['seed'], ml['trueBStr'], rallDescr))
                    continue
                obj = []
                # Find best fit?
                for mlocal in mlocall:
                    obj.append(mlocal['obj'])
                iMin = np.argmin(obj)
                objAll[iml, :, ns] = obj
                objIntAll[iml, ns] = ml['objInt']
                ''' {'candidateB': b, 'obj': obj[ib], 'Phi': Phi,  'ttestl': ttestl, 'mul': mul, 'varl': varl} '''
                for im, mlocal in enumerate(mlocall):
                    if(ir == 0 and (ns == 1 or ns == 2)):
                        if((fPlotBestFit and iMin == im) or fPlotAllFits):
                            print('plotting sample')
                            v.plotBranchModel(mlocal['candidateB'], ml['pt'], ml['Y'],
                                              mlocal['ttestl'], mlocal['mul'], mlocal['varl'],
                                              mlocal['Phi'], fPlotPhi=True, fPlotVar=True)
                            plt.title('%s:%g: TB=%s b=%g NLL=%.1f NULL=%.1f' % (rallDescr[ir], ns, ml['trueBStr'],
                                                                            mlocal['candidateB'],
                                                                            mlocal['obj'], ml['objInt']))
                            a = plt.gca()
                            ax2 = a.twinx()
                            ax2.bar(BgridSearchAll, np.exp(-ml['obj'])/np.exp(-ml['obj']).sum(), color='g', width=0.01)
                            ax2.set_ylabel('p(B)', color='green')
                        else:
                            pass
        # save data
        np.savez(strDataDir+'analyseGridFiles%s.npz' % rallDescr[ir],
                 objAll=objAll, BgridSearchAll=BgridSearchAll, BtryAll=BtryAll, objIntAll=objIntAll)
        # Plot objective function for full/sparse
        assert len(BtryAll) == 4 or len(BtryAll) == 2, 'for plotting assume 4 or 2 real branching locations'
        f, axarr = plt.subplots(2, 2, sharex=True, sharey=False, figsize=(10, 10))
        plt.title(rallDescr[ir])
        ax = axarr.flatten()
        for ib, btrue in enumerate(BtryAll):
            if(np.isnan(btrue)):
                stb = 'Ind'
            else:
                stb = str(btrue)
#             plt.boxplot(objAll[ib, :, :].T, labels=BgridSearchAll)
            ax[ib].plot(BgridSearchAll, objAll[ib, :, :])
            ax[ib].set_title('%s: Likelihood samples %g TrueB=%s' % (rallDescr[ir], len(res), stb))
            if(~np.isnan(btrue)):
                vax = ax[ib].axis()
                ax[ib].plot([btrue, btrue], vax[-2:], '--g', linewidth=3)
        '''
        Plot errors in branching point identification
        bTrue - S[im, 0] except for integrated where we show Sim[im, 0]
        So the larger the value the bigger the error.
        The more positive, the more we underestimate the branching pt
        The more negative the more we overshoot
        '''
        f, axarr = plt.subplots(2, 2, sharex=True, sharey=False, figsize=(10, 10))
        ax = axarr.flatten()
        for ib, btrue in enumerate(BtryAll):
            if(np.isnan(btrue)):
                stb = 'Ind'
            else:
                stb = str(btrue)
            ax[ib].hist(errorInBranchingPtAll[ib, :])
            ax[ib].set_title('%s: Histogram of branching error samples %g TrueB=%s' % (rallDescr[ir], len(res), stb))
            vax = ax[ib].axis()
            ax[ib].plot([0, 0], vax[-2:], '--g', linewidth=3)  # the reference line
        # Plot evidence for branching
        f, axarr = plt.subplots(2, 2, sharex=True, sharey=False, figsize=(10, 10))
        ax = axarr.flatten()
        for ib, btrue in enumerate(BtryAll):
            if(np.isnan(btrue)):
                stb = 'Ind'
            else:
                stb = str(btrue)
            ax[ib].hist(logLikelihoodRatioAll[ib, :])
            ax[ib].set_title('%s: Histogram of log likelihood ratios %g TrueB=%s' % (rallDescr[ir], len(res), stb))
            vax = ax[ib].axis()
            ax[ib].plot([0, 0], vax[-2:], '--g', linewidth=3)  # the further negative the more evidence for branching
    # timing info: box plot of full/sparse for each candidate branching point
    f, axarr = plt.subplots(1, sharex=True, sharey=False, figsize=(10, 10))
    t = np.zeros((len(BgridSearchAll)*len(rall), len(Btry)*len(res)))
    leg = list()
    for i in range(len(BgridSearchAll)):
        t[i*2, :] = timingInfoAll[0, :, i, :].flatten()  # full model
        t[i*2+1, :] = timingInfoAll[1, :, i, :].flatten()  # sparse model
        leg.append('F%.1f' % BgridSearchAll[i])
        leg.append('S%.1f' % BgridSearchAll[i])
    axarr.boxplot(t.T, labels=leg)
    # timing info: box plot of full/sparse for each candidate branching point
    f, axarr = plt.subplots(1, sharex=True, sharey=False, figsize=(10, 10))
    t = np.zeros((len(rall), len(Btry)*len(res)*len(BgridSearchAll)))
    leg = list()
    t[0, :] = timingInfoAll[0, :, :, :].flatten()  # full model
    t[1, :] = timingInfoAll[1, :, :, :].flatten()  # sparse model
    leg.append('Full')
    leg.append('Sparse')
    axarr.boxplot(t.T, labels=leg)

 # f, axarr = plt.subplots(2, sharex=True, sharey=False, figsize=(10, 10))
# v.plotBranchModel(mlocal['candidateB'], ml['pt'], ml['Y'],
#                   mlocal['ttestl'], mlocal['mul'], mlocal['varl'],
#                   mlocal['Phi'], fPlotPhi=True, fPlotVar=True)
# plt.title('%s:TB=%s b=%g NLL=%.1f NULL=%.1f' % (rallDescr[ir], ml['trueBStr'],
#                                                 mlocal['candidateB'],
#                                                 mlocal['obj'], ml['objInt']))
# ax1 = f.add_subplot(gs1[0])
# ax2 = f.add_subplot(gs1[1])
# ax2.bar(BgridSearchAll, np.exp(-ml['obj'])/np.exp(-ml['obj']).sum(), color='g', width=0.01)
# ax2.set_ylabel('p(B)', color='green')

