''' Module to replace branch_kern with parameterised version'''
from . import VBHelperFunctions
import GPflow
from GPflow.param import DataHolder
import tensorflow as tf
import numpy as np
from matplotlib import pyplot as plt


def PlotSample(X, samples, B=None, lw=3., fs=10, figsizeIn=(5, 5)):
    D = samples.shape[1]  # number of outputs
    assert X.shape[0] == samples.shape[0]
    M = 3  # number of functions
    assert B is None or B.size == 1, 'Limited to one branch point'
    _, ax = plt.subplots(D, 1, figsize=figsizeIn, sharex=True, sharey=True)
    for d in range(D):
        for i in range(1, M + 1):
            t = X[X[:, 1] == i, 0]
            y = samples[X[:, 1] == i, d]
            if(t.size == 0):
                continue
            if(D != 1):
                p = ax.flatten()[d]
            else:
                p = ax
            p.plot(t, y, '-+', label=i, markersize=2 * lw)
            p.text(t[t.size / 2], y[t.size / 2], str(i), fontsize=fs)
        # Add vertical lines for branch points
        if(B is not None):
            v = p.axis()
            p.set_title('Branching kernel at B=%g' % B)
            for i in range(B.size):
                p.plot([B[i], B[i]], v[-2:], '--r')


def SampleKernel(kern, X, D=1, tol=1e-6, retChol=False):
    ''' Sample GP, D is number of independent output dimensions '''
    K = kern.compute_K(X, X)  # NxM
    L = np.linalg.cholesky(K + np.eye(K.shape[0]) * tol)
    samples = L.dot(np.random.randn(L.shape[0], D))
    if(retChol):
        return samples, L, K
    else:
        return samples


class BranchKernelParam(GPflow.kernels.Kern):

    def __init__(self, base_kern, branchPtTensor, b, fDebug=False):
        ''' branchPtTensor is tensor of branch points of size F X F X B where F the number of
        functions and B the number of branching points '''
        self.kern = base_kern
        self.fm = branchPtTensor
        self.fDebug = fDebug
        assert isinstance(b, np.ndarray)
        assert self.fm.shape[0] == self.fm.shape[1]
        assert self.fm.shape[2] > 0
        self.Bv = DataHolder(b)
        GPflow.kernels.Kern.__init__(self, input_dim=base_kern.input_dim + 1)

    def SampleKernel(self, XExpanded, b=None, tol=1e-6):
        if(b is not None):
            self.Bv = np.ones((1, 1))*b
        XTree = VBHelperFunctions.SetXExpandedBranchingPoint(XExpanded, self.Bv.value)
        return SampleKernel(self, XTree, tol=tol), XTree

    def K(self, X, Y=None):
        if Y is None:
            Y = X  # hack to avoid duplicating code below

        if(self.fDebug):
            print('Compiling kernel')
        t1s = tf.expand_dims(X[:, 0], 1)  # N X 1
        t2s = tf.expand_dims(Y[:, 0], 1)
        i1s_r = tf.expand_dims(X[:, 1], 1)
        i2s_r = tf.expand_dims(Y[:, 1], 1)
        if(self.fDebug):
            snl = 10  # how many entries to print
            i1s = tf.Print(i1s_r, [tf.shape(i1s_r), i1s_r], message='i1s=',
                           name='i1sdebug', summarize=snl)  # will print message
            i2s = tf.Print(i2s_r, [tf.shape(i2s_r), i2s_r], message='i2s=',
                           name='i2sdebug', summarize=snl)  # will print message
        else:
            i1s = i1s_r
            i2s = i2s_r

        i1s_matrix = tf.tile(i1s, tf.reverse(tf.shape(i2s), [True]))
        i2s_matrix = tf.tile(i2s, tf.reverse(tf.shape(i1s), [True]))
        i2s_matrixT = tf.transpose(i2s_matrix)

        Ktts = self.kern.K(t1s, t2s)  # N*M X N*M
        with tf.name_scope("kttscope"):  # scope
            same_functions = tf.equal(i1s_matrix, tf.transpose(i2s_matrix), name='FiEQFj')
            K_s = tf.select(same_functions, Ktts, Ktts, name='selectFiEQFj')  # just setup matrix with block diagonal

        m = self.fm.shape[0]
        for fi in range(m):
            for fj in range(m):
                if (fi != fj):
                    with tf.name_scope("f" + str(fi) + "f" + str(fj)):  # scope
                        # much easier to remove nans before tensorflow
                        bnan = self.fm[fi, fj, ~np.isnan(self.fm[fi, fj, :])]
                        fi_s = tf.constant(fi + 1, tf.int32, name='function' + str(fi))
                        fj_s = tf.constant(fj + 1, tf.int32, name='function' + str(fj))

                        i1s_matrixInt = tf.cast(i1s_matrix, tf.int32, name='casti1s')
                        i2s_matrixTInt = tf.cast(i2s_matrixT, tf.int32, name='casti2s')

                        fiFilter = fi_s * tf.ones_like(i1s_matrixInt, tf.int32, name='fiFilter')
                        fjFilter = fj_s * tf.ones_like(i2s_matrixTInt, tf.int32, name='fjFilter')  # must be transpose

                        f1F = tf.equal(i1s_matrixInt, fiFilter, name='indexF' + str(fi))
                        f2F = tf.equal(i2s_matrixTInt, fjFilter, name='indexF' + str(fj))

                        t12F = tf.logical_and(f1F, f2F, name='F' + str(fi) + 'andF' + str(fj))

                        # Get the actual values of the Bs = B[index of relevant branching points]
                        bint = bnan.astype(int)  # convert to int - set of indexes
                        if(self.fDebug):
                            Br = tf.Print(self.Bv, [tf.shape(self.Bv), self.Bv], message='Bv=', name='Bv', summarize=3)  # will print message
                        else:
                            Br = self.Bv
                        Bs = ((tf.concat(0, [tf.slice(Br, [i - 1, 0], [1, 1]) for i in bint])))

                        kbb = self.kern.K(Bs) + tf.diag(tf.ones(tf.shape(Bs)[:1], dtype=tf.float64)) * 1e-6
                        if(self.fDebug):
                            kbb = tf.Print(kbb, [tf.shape(kbb), kbb], message='kbb=', name='kbb', summarize=10)
                            kbb = tf.Print(kbb, [self.kern.lengthscales], message='lenscales=', name='lenscales', summarize=10)
                            kbb = tf.Print(kbb, [self.kern.variance], message='variance=', name='lenscales', summarize=10)
                            kbb = tf.Print(kbb, [Bs], message='Bs=', name='Bs', summarize=10)

                        Kbbs_inv = tf.matrix_inverse(kbb, name='invKbb')  # B X B
                        Kb1s = self.kern.K(t1s, Bs)  # N*m X B
                        Kb2s = self.kern.K(t2s, Bs)  # N*m X B

                        a = tf.matmul(Kb1s, Kbbs_inv)
                        K_crosss = tf.matmul(a, tf.transpose(Kb2s), name='Kt1_Bi_invBB_KBt2')

                        K_s = tf.select(t12F, K_crosss, K_s, name='selectIndex')
        return K_s

    def Kdiag(self, X):
        return tf.diag_part(self.kern.K(X))  # diagonal is just single point no branch point relevant


class IndKern(GPflow.kernels.Kern):
    ''' an independent output kernel '''
    def __init__(self, base_kern):
        GPflow.kernels.Kern.__init__(self, input_dim=base_kern.input_dim + 1)
        self.kern = base_kern

    def K(self, X, Y=None):
        if Y is None:
            t1 = X[:, :-1]
            i1 = X[:, -1:]
            Ktt = self.kern.K(t1)

            i1_matrix = tf.tile(i1, tf.reverse(tf.shape(i1), [True]))

            same_functions = tf.equal(i1_matrix, tf.transpose(i1_matrix))
            K_s = tf.select(same_functions, Ktt, tf.zeros_like(Ktt))
            return K_s
        else:
            t1 = tf.expand_dims(X[:, 0], 1)
            t2 = tf.expand_dims(Y[:, 0], 1)
            i1 = tf.expand_dims(X[:, 1], 1)
            i2 = tf.expand_dims(Y[:, 1], 1)

            Ktt = self.kern.K(t1, t2)

            i1_matrix = tf.tile(i1, tf.reverse(tf.shape(i2), [True]))
            i2_matrix = tf.tile(i2, tf.reverse(tf.shape(i1), [True]))

            same_functions = tf.equal(i1_matrix, tf.transpose(i2_matrix))
            K_s = tf.select(same_functions, Ktt, tf.zeros_like(Ktt))
            return K_s

    def Kdiag(self, X):
        return tf.diag_part(self.kern.K(X))


