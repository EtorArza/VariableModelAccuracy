
#==================================================================================================
# LIBRERÍAS
#==================================================================================================
import numpy as np
import matplotlib as mpl
import scipy as sc
import matplotlib.pyplot as plt
import scipy.integrate as scint
import time
import os
from scipy.interpolate import interp1d
from scipy.interpolate import LSQUnivariateSpline as lsqus
from scipy.integrate import simpson
from operator import itemgetter
import openpyxl
import pickle
import copy
from functools import partial
from scipy.interpolate import interp1d
from typing import Union
import cma

import sys
sys.path.append("OptimizationAlgorithms_KONFLOT/packages")

import turbine_classes
import MathTools as mt
import time

from cma.utilities import utils 
import pandas as pd
from tqdm import tqdm

#==================================================================================================
# CLASES
#==================================================================================================

class stopwatch:
    
    def __init__(self):
        self.reset()

    def reset(self):
        self.start_t = time.time()
        self.pause_t=0

    def pause(self):
        self.pause_start = time.time()
        self.paused=True

    def resume(self):
        if self.paused:
            self.pause_t += time.time() - self.pause_start
            self.paused = False

    def get_time(self):
        return time.time() - self.start_t - self.pause_t


#==================================================================================================
# FUNCIONES
#==================================================================================================
def define_bounds():

	# Definir rangos de los parámetros que definen el diseño de la turbina.
	sigma_hub = [0.4, 0.7]# Hub solidity gene.
	sigma_tip = [0.4, 0.7]# Tip solidity gene.
	nu = [0.4, 0.75] # Hub-to-tip-ratio gene.
	tip_clearance=[0,3]# Tip-clearance gene.	  
	airfoil_dist = np.arange(0, 27)# Airfoil dist. gene.  

	# Array con los rangos.
	bounds=np.array([
	[sigma_hub[0]    , sigma_hub[1]],
	[sigma_tip[0]    , sigma_tip[1]],
	[nu[0]           , nu[1]],
	[tip_clearance[0], tip_clearance[1]],
	[0               , 26]
	])

	return bounds

def build_constargs_dict(N):
	# Definir parámetros constantes.
	omega = 2100# Rotational speed.
	rcas = 0.4# Casing radius.
	airfoils = ["NACA0015", "NACA0018", "NACA0021"]# Set of possible airfoils.
	polars = turbine_classes.polar_database_load(filepath="OptimizationAlgorithms_KONFLOT/", pick=False)# Polars.
	cpobjs = [933.78, 1089.41, 1089.41, 1011.59, 1011.59, 1011.59, 933.78, 933.78, 933.78, 855.96]# Target dumping coefficients.
	devobjs = [2170.82, 2851.59, 2931.97, 2781.80, 2542.296783, 4518.520988, 4087.436172, 3806.379812, 5845.986619, 6745.134759]# Input sea-state standard pressure deviations.
	weights = [0.1085, 0.1160, 0.1188, 0.0910, 0.0824, 0.1486, 0.0882, 0.0867, 0.0945, 0.0652]# Input sea-state weights.
	Nmin = 1000#Max threshold rotational speeds
	Nmax = 3200#Min threshold rotational speeds

	# Construir el diccionario que necesita la función fitness
	constargs = {"N": N,
		     "omega": omega,
		     "rcas": rcas,
		     "airfoils": airfoils,
		     "polars": polars,
		     "cpobjs": cpobjs,
		     "devobjs": devobjs,
		     "weights": weights,
		     "Nmin": Nmin,
		     "Nmax": Nmax,
		     "Mode": "mono"}

	return constargs

def fitness_function(turb_params,N=50):

	# Construir diccionario de parámetros constantes.
	constargs=build_constargs_dict(N)

	# Crear turbina instantantanea.
	os.chdir('OptimizationAlgorithms_KONFLOT')
	turb = turbine_classes.instantiate_turbine(constargs, turb_params)	
	os.chdir('../')

	# Calcular evaluación.
	sw.resume()
	scores = turbine_classes.fitness_func(constargs=constargs, turb=turb, out='brfitness')
	sw.pause()

	return -scores[1] 

def scale_x(x,bounds):
    return x * (bounds[:,1] - bounds[:,0]) + bounds[:,0]

def invert_scale_x(x,bounds):
	return (x - bounds[:,0])/(bounds[:,1] - bounds[:,0]) 

def transform_turb_params(x, blade_number,bounds):
    scaled_x = scale_x(x,bounds)
    return [blade_number]+list(scaled_x[:-1])+[round(scaled_x[-1])]

def evaluate(blade_number,bounds,N,seed):

	# Inicializar contadores de tiempo y número de evaluaciones.
	global sw
	sw = stopwatch()
	sw.pause()
	n_eval=0
	
	# Para la precisión máxima de N.
	if N==default_N:
		# Inicializar CMA-ES
		np.random.seed(seed)
		es = cma.CMAEvolutionStrategy(np.random.random(5), 0.33,inopts={'bounds': [0, 1],'seed':seed})

		# Para guardar las configuraciones evaluadas.
		df_turb_params=[]

		while not es.stop():

			# Nueva generación.
			solutions = es.ask()

			# Evaluar nuevas soluciones e ir guardando tiempos.
			new_scores=[]
			for x in solutions:
				# Contar una nueva evaluación.
				n_eval+=1

				# Transformación de parámetros.
				turb_params=transform_turb_params(x, blade_number,bounds)
				df_turb_params.append(turb_params)

				# Calcular score.
				new_score=fitness_function(turb_params, N)
				new_scores.append(new_score)

				# Añadir nuevos datos a la base de datos.
				df.append([N,seed,n_eval,-new_score,sw.get_time()])

			# Pasar los valores de la función objetivo para prepararse para la próxima iteración.
			es.tell(solutions, new_scores)
			es.logger.add()  

			# Imprimir las variables del estado actual en una sola línea.
			es.disp()

		# Guardar la base de datos con las configuraciones evaluadas.
		df_turb_params=pd.DataFrame(df_turb_params)
		df_turb_params.to_csv('results/data/CMA_ES_GeneralAnalysis/df_turb_param_blade_number'+str(blade_number)+'_seed'+str(seed)+'_N50.csv')
	
	# Cuando no consideramos la precisión máxima de N.
	else:

		# Para guardar las configuraciones evaluadas.
		df_turb_params=[]

		# Cargar las turbinas evaluadas con la precisión total.
		df_turb_params_max_acc=pd.read_csv('results/data/CMA_ES_GeneralAnalysis/df_turb_param_blade_number'+str(blade_number)+'_seed'+str(seed)+'_N50.csv', index_col=0)

		# Empezar por evaluar las mismas turbinas evaluadas con la precisión total.
		row=0
		while sw.get_time()<max_time and row<df_turb_params_max_acc.shape[0]:
			# Contar una nueva evaluación.
			n_eval+=1

			# Parámetros.
			turb_params=df_turb_params_max_acc.iloc[row]
			df_turb_params.append(list(turb_params))

			# Calcular score.
			new_score=fitness_function(turb_params, N)

			# Añadir nuevos datos a la base de datos.
			df.append([N,seed,n_eval,-new_score,sw.get_time()])

			# Actualizar contador de fila.
			row+=1

		# Al terminar con las turbinas evaluadas por la precisión total si sobra tiempo,
		# evaluar nuevas turbinas usando CMA-ES partiendo de la última turbina evaluada,
		# en lugar de una aleatoria inicial.
		if sw.get_time()<max_time:

			# Inicializar CMA-ES
			init_turb_param=df_turb_params_max_acc.iloc[df_turb_params_max_acc.shape[0]-1]
			init_turb_param=invert_scale_x(init_turb_param[1:],bounds)
			es = cma.CMAEvolutionStrategy(init_turb_param, 0.33,inopts={'bounds': [0, 1],'seed':seed})

			while not es.stop():

				# Nueva generación.
				solutions = es.ask()

				# Evaluar nuevas soluciones e ir guardando tiempos.
				new_scores=[]
				for x in solutions:
					# Contar una nueva evaluación.
					n_eval+=1

					# Transformación de parámetros.
					turb_params=transform_turb_params(x, blade_number,bounds)
					df_turb_params.append(turb_params)

					# Calcular score.
					new_score=fitness_function(turb_params, N)
					new_scores.append(new_score)

					# Añadir nuevos datos a la base de datos.
					df.append([N,seed,n_eval,-new_score,sw.get_time()])

				# Pasar los valores de la función objetivo para prepararse para la próxima iteración.
				es.tell(solutions, new_scores)
				es.logger.add()  

				# Imprimir las variables del estado actual en una sola línea.
				es.disp()

		# Guardar la base de datos con las configuraciones evaluadas.
		df_turb_params=pd.DataFrame(df_turb_params)
		df_turb_params.to_csv('results/data/CMA_ES_GeneralAnalysis/df_turb_param_blade_number'+str(blade_number)+'_seed'+str(seed)+'_N'+str(N)+'.csv')



def new_stop(self, check=True, ignore_list=(), check_in_same_iteration=False,
             get_value=None):
	stop={}
	if sw.get_time()>max_time:
		stop={'TIME RUN OUT':max_time}
	return stop

#==================================================================================================
# PROGRAMA PRINCIPAL
#==================================================================================================

# Para usar la nueva función de parada (según el tiempo de ejecución).
cma.CMAEvolutionStrategy.stop=new_stop

# Definir array de rangos de los parámetros a optimizar (blase_number de forma individual).
bounds=define_bounds()
list_blade_number = [3, 5, 7]# Blade-number gene.

# Mallados y parámetros.
list_seeds=range(0,10,1)
list_acc=[1.0,0.8,0.6,0.4]
max_time=60*9
default_N=50

#--------------------------------------------------------------------------------------------------
# BLADE-NUMBER=3
#--------------------------------------------------------------------------------------------------
# Fijar blade-number.
blade_number = list_blade_number[0]

# Guardar datos asociados a cada accuracy en una base de datos.
for accuracy in list_acc:

	# Inicializar base de datos.
	df=[]

	# Fijar valor de N.
	N=int(default_N*accuracy)
	
	for seed in tqdm(list_seeds):
		# Evaluación.
		evaluate(blade_number,bounds,N,seed)

	# Guardar datos acumulados.
	df=pd.DataFrame(df,columns=['N','seed','n_eval','score','time'])
	df.to_csv('results/data/Turbines/CMA_ES_GeneralAnalysis/df_blade_number'+str(blade_number)+'_acc'+str(accuracy)+'.csv')

# Guardar lista de accuracys.
np.save('results/data/Turbines/CMA_ES_GeneralAnalysis/list_acc',list_acc)


		
		
		





