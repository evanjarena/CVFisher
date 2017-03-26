#! /usr/bin/env python
'''
Calculates the expected sensitivity of a 21cm experiment to a given 21cm power spectrum.  Requires as input an array .npz file created with mk_array_file.py.
'''
import aipy as a, numpy as n, optparse, sys
from scipy import interpolate, integrate

o = optparse.OptionParser()
o.set_usage('calc_sense.py [options] *.npz')
o.set_description(__doc__)
o.add_option('-R', '--RestFreq', dest='restFreq', default=1.42040575177, type=float,
        help="Rest frequency of spectral line in question. In GHz")
o.add_option('-T', '--Tsky', dest='Tsky', default=300, type=float,
    help="Sky temperature (in K) at the center frequency of the observation.")
o.add_option('-m', '--model', dest='model', default='mod',
    help="The model of the foreground wedge to use.  Three options are 'pess' (all k modes inside horizon + buffer are excluded, and all baselines are added incoherently), 'mod' (all k modes inside horizon + buffer are excluded, but all baselines within a uv pixel are added coherently), and 'opt' (all modes k modes inside the primary field of view are excluded).  See Pober et al. 2014 for more details.")
o.add_option('-b', '--buff', dest='buff', default=0.1, type=float,
    help="The size of the additive buffer outside the horizon to exclude in the pessimistic and moderate models.")
o.add_option('-f', '--freq', dest='freq', default=.135, type=float,
    help="The center frequency of the observation in GHz.  If you change from the default, be sure to use a sensible power spectrum model from that redshift.  Note that many values in the code are calculated relative to .150 GHz and are not affected by changing this value.")
o.add_option('--eor', dest='eor', default='ps_no_halos_nf0.521457_z9.50_useTs0_zetaX-1.0e+00_200_400Mpc_v2',
    help="The model epoch of reionization power spectrum.  The code is built to handle output power spectra from 21cmFAST.")
o.add_option('--ndays', dest='ndays', default=180., type=float,
    help="The total number of days observed.  The default is 180, which is the maximum a particular R.A. can be observed in one year if one only observes at night.  The total observing time is ndays*n_per_day.")
o.add_option('--n_per_day', dest='n_per_day', default=6., type=float,
    help="The number of good observing hours per day.  This corresponds to the size of a low-foreground region in right ascension for a drift scanning instrument.  The total observing time is ndays*n_per_day.  Default is 6.  If simulating a tracked scan, n_per_day should be a multiple of the length of the track (i.e. for two three-hour tracks per day, n_per_day should be 6).")
o.add_option('--bwidth', dest='bwidth', default=0.008, type=float,
    help="Cosmological bandwidth in GHz.  Note this is not the total instrument bandwidth, but the redshift range that can be considered co-eval.  Default is 0.008 (8 MHz).")
o.add_option('--nchan', dest='nchan', default=82, type=int,
    help="Integer number of channels across cosmological bandwidth.  Defaults to 82, which is equivalent to 1024 channels over 100 MHz of bandwidth.  Sets maximum k_parallel that can be probed, but little to no overall effect on sensitivity.")
o.add_option('--no_ns', dest='no_ns', action='store_true',
    help="Remove pure north/south baselines (u=0) from the sensitivity calculation.  These baselines can potentially have higher systematics, so excluding them represents a conservative choice.")
opts, args = o.parse_args(sys.argv[1:])
restFreq = opts.restFreq

#=========================COSMOLOGY/BINNING FUNCTIONS=========================

preFac = 0.299792458 * 10**6 / 100. # c / (100 km/s/Mpc)

#Convert frequency (GHz) to redshift for 21cm line.
def f2z(fq):
    return (restFreq / fq - 1)

def z2D(z,Omm = 0.309375,OmL = 1-0.309375):
    return preFac * integrate.quad(lambda x: 1./n.sqrt(OmL + Omm * (1+x)**3), 0, z)[0]

#Multiply by this to convert an angle on the sky to a transverse distance in Mpc/h at redshift z
dL_dth = interpolate.interp1d(n.linspace(0.,200.,5000),map(z2D,n.linspace(0.,200.,5000)),bounds_error=False,fill_value=-1)
#Version below only works for z ~ reionization.
# def dL_dth(z):
#     '''[h^-1 Mpc]/radian, from Furlanetto et al. (2006)'''
#     return 1.9 * (1./a.const.arcmin) * ((1+z) / 10.)**.2

#Multiply by this to convert a bandwidth in GHz to a line of sight distance in Mpc/h at redshift z
def dL_df(z,Omm = 0.309375,OmL = 1-0.309375):
    return preFac * (1 + z)**2 / (restFreq * n.sqrt(OmL + Omm * (1+z)**3) )
#Version below only works for z ~ reionization.
# def dL_df(z, omega_m=0.266):
#     '''[h^-1 Mpc]/GHz, from Furlanetto et al. (2006)'''
#     return (1.7 / 0.1) * ((1+z) / 10.)**.5 * (omega_m/0.15)**-0.5 * 1e3

#Multiply by this to convert a baseline length in wavelengths (at the frequency corresponding to redshift z) into a tranverse k mode in h/Mpc at redshift z
def dk_du(z):
    '''2pi * [h Mpc^-1] / [wavelengths], valid for u >> 1.'''
    return 2*n.pi / dL_dth(z) # from du = 1/dth, which derives from du = d(sin(th)) using the small-angle approx

#Multiply by this to convert eta (FT of freq.; in 1/GHz) to line of sight k mode in h/Mpc at redshift z
def dk_deta(z):
    '''2pi * [h Mpc^-1] / [GHz^-1]'''
    return 2*n.pi / dL_df(z)

#scalar conversion between observing and cosmological coordinates
def X2Y(z):
    '''[h^-3 Mpc^3] / [str * GHz]'''
    return dL_dth(z)**2 * dL_df(z)

#A function used for binning
def find_nearest(array,value):
    idx = (n.abs(array-value)).argmin()
    return idx


#====================OBSERVATION/COSMOLOGY PARAMETER VALUES====================

#Load in data from array file; see mk_array_file.py for definitions of the parameters
array = n.load(args[0])
name = array['name']
obs_duration = array['obs_duration']
dish_size_in_lambda = array['dish_size_in_lambda']
Trx = array['Trx']
t_int = array['t_int']
if opts.model == 'pess':
    uv_coverage = array['uv_coverage_pess']
else:
    uv_coverage = array['uv_coverage']

h = 0.67610
B = opts.bwidth
z = f2z(opts.freq)


# Next line no longer necessary because the new mk_array_file.py i.e. mk_array_file_z.py
# does this step now
#dish_size_in_lambda = dish_size_in_lambda*(opts.freq/.150) # linear frequency evolution, relative to 150 MHz
# print obs_duration
# assert False
first_null = 1.22/dish_size_in_lambda #for an airy disk, even though beam model is Gaussian
bm = 1.13*(2.35*(0.45/dish_size_in_lambda))**2
nchan = opts.nchan
kpls = dk_deta(z) * n.fft.fftfreq(nchan,B/nchan)

Tsky = 1e3 * opts.Tsky  # sky temperature in mK
n_lstbins = opts.n_per_day*60./obs_duration

#===============================EOR MODEL===================================

#You can change this to have any model you want, as long as mk, mpk and p21 are returned

modelfile = opts.eor
model = n.load(modelfile)
mk, mpk = model['ks']/h, h**3 * model['Pz0'] #k, T^2 P_m(k,z)
#note that we're converting from Mpc to h/Mpc
bias = model['bz0']
growth_f = model['fz0']

#interpolation function for the EoR model
p21 = interpolate.interp1d(mk, mpk, kind='linear')

#=================================MAIN CODE===================================

#set up blank arrays/dictionaries
kprs = []
#sense will include sample variance, Tsense will be Thermal only
sense, Tsense, pkdic, wedic= {}, {}, {}, {}
    
uv_coverage *= t_int
SIZE = uv_coverage.shape[0]

# Cut unnecessary data out of uv coverage: auto-correlations & half of uv plane (which is not statistically independent for real sky)
uv_coverage[SIZE/2,SIZE/2] = 0.
uv_coverage[:,:SIZE/2] = 0.
uv_coverage[SIZE/2:,SIZE/2] = 0.
if opts.no_ns: uv_coverage[:,SIZE/2] = 0.



#loop over uv_coverage to calculate k_pr
nonzero = n.where(uv_coverage > 0)
for iu,iv in zip(nonzero[1], nonzero[0]):
   u, v = (iu - SIZE/2) * dish_size_in_lambda, (iv - SIZE/2) * dish_size_in_lambda
   umag = n.sqrt(u**2 + v**2)
   kpr = umag * dk_du(z)
   kprs.append(kpr)
   #calculate horizon limit for baseline of length umag
   if opts.model in ['mod','pess']: hor = dk_deta(z) * umag/opts.freq + opts.buff
   elif opts.model in ['opt']: hor = dk_deta(z) * (umag/opts.freq)*n.sin(first_null/2)
   else: print '%s is not a valid foreground model; Aborting...' % opts.model; sys.exit()
   if not sense.has_key(kpr):
       #print kpr
       sense[kpr] = n.zeros_like(kpls)
       Tsense[kpr] = n.zeros_like(kpls)
       pkdic[kpr] = n.zeros_like(kpls)
       wedic[kpr] = n.zeros_like(kpls)
   for i, kpl in enumerate(kpls):
       #exclude k_parallel modes contaminated by foregrounds
       if n.abs(kpl) < hor: continue
       k = n.sqrt(kpl**2 + kpr**2)
       mu = kpl / k
       if k < min(mk): continue
       #don't include values beyond the interpolation range (no sensitivity anyway)
       if k > n.max(mk): continue
       tot_integration = uv_coverage[iv,iu] * opts.ndays
       pspec = p21(k) * (bias + growth_f * mu**2)**2
       Tsys = Tsky + Trx
       bm2 = bm/2. #beam^2 term calculated for Gaussian; see Parsons et al. 2014
       bm_eff = bm**2 / bm2 # this can obviously be reduced; it isn't for clarity
       scalar = X2Y(z) * bm_eff * B
       Trms = Tsys / n.sqrt(2*(B*1e9)*tot_integration)
       #add errors in inverse quadrature
       sense[kpr][i] += 1./(scalar*Trms**2 + pspec)**2
       Tsense[kpr][i] += 1./(scalar*Trms**2)**2
       pkdic[kpr][i] += pspec
       wedic[kpr][i] += 1.0

#bin the result in 1D
delta = dk_deta(z)*(1./B) #default bin size is given by bandwidth
kmag = n.arange(delta,n.max(mk),delta)

kprs = n.unique(kprs)
kpl_folded = n.linspace(0.,n.max(abs(kpls)),len(kpls)/2+1)
print kpl_folded[:10]
#
## anze debug##
shawks=n.arange(50)*0.1+0.05
kprs=shawks*1.0
kpl_folded=shawks*1.0
###

sense_cylind = n.zeros((len(kprs),len(kpl_folded)))
Tsense_cylind = n.zeros((len(kprs),len(kpl_folded)))
pk_cylind = n.zeros((len(kprs),len(kpl_folded)))
we_cylind = n.zeros((len(kprs),len(kpl_folded)))
for ind, kpr in enumerate(sense.keys()):
    #errors were added in inverse quadrature, now need to invert and take square root to have error bars; also divide errors by number of indep. fields
    sense[kpr] = sense[kpr]**-.5 / n.sqrt(n_lstbins)
    Tsense[kpr] = Tsense[kpr]**-.5 / n.sqrt(n_lstbins)
    for i, kpl in enumerate(kpls):
        k = n.sqrt(kpl**2 + kpr**2)
        if k > n.max(mk): continue
        #add errors in inverse quadrature for further binning
        pair=find_nearest(kprs,kpr),find_nearest(kpl_folded,abs(kpl))
        sense_cylind[pair] += 1./sense[kpr][i]**2
        Tsense_cylind[pair] += 1./Tsense[kpr][i]**2
        pk_cylind[pair] += pkdic[kpr][i]
        we_cylind[pair] += wedic[kpr][i]
#invert errors and take square root again for final answer
sense_cylind = sense_cylind**-0.5
Tsense_cylind = Tsense_cylind**-0.5
pk_cylind/=we_cylind

print pk_cylind.shape
print pk_cylind[5:10,5:10],'signal'

print Tsense_cylind[10,10],'sens'
print (pk_cylind/sense_cylind)[10,10],'snr'
print (pk_cylind/Tsense_cylind)[10,10],'snr'

import matplotlib.pyplot as plt
plt.imshow(n.log10(Tsense_cylind.T),origin='lower', vmin=-3.7,vmax=-2)
plt.colorbar()
plt.show()

stop()

# for ind,kbin in enumerate(sense_cylind):
#     sense1d[ind] = kbin**-.5
#     Tsense1d[ind] = Tsense1d[ind]**-.5


#print sense_cylind.shape, kprs.shape, kpl_folded.shape, sense_cylind.shape
#save results to output npz
n.savez('%s_%s_%.8f_cylind.npz' % (name,opts.model,opts.freq),kperps=kprs,kparas=kpl_folded,errs=sense_cylind,T_errs=Tsense_cylind)

#calculate significance
snr = 0.
for i, kperp in enumerate(kprs):
  for j, kpara in enumerate(kpl_folded):
    k = n.sqrt(kpara**2 + kperp**2)
    if k < n.min(mk) or k > n.max(mk): continue
    mu = kpara / k
    pspec = p21(k) * (bias + growth_f * mu**2)**2
    snr += (pspec / sense_cylind[i,j])**2
print 'total snr = ', n.sqrt(snr), ' at redshift ', z

