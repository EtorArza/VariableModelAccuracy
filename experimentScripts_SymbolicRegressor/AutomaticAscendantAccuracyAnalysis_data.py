#==================================================================================================
# LIBRERÍAS
#==================================================================================================
# Para mi código.
from gplearn.genetic import SymbolicRegressor
from sklearn.utils.random import check_random_state
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt
import numpy as np
import graphviz
import pandas as pd
from tqdm import tqdm
import scipy as sc
import random

# Para las modificaciones.
import itertools
from abc import ABCMeta, abstractmethod
from time import time
from warnings import warn
import numpy as np
from joblib import Parallel, delayed
from scipy.stats import rankdata
from sklearn.base import BaseEstimator
from sklearn.base import RegressorMixin, TransformerMixin, ClassifierMixin
from sklearn.exceptions import NotFittedError
from sklearn.utils import compute_sample_weight
from sklearn.utils.validation import check_array, _check_sample_weight
from sklearn.utils.multiclass import check_classification_targets
from gplearn._program import _Program
from gplearn.fitness import _fitness_map, _Fitness
from gplearn.functions import _function_map, _Function, sig1 as sigmoid
from gplearn.utils import _partition_estimators
from gplearn.utils import check_random_state

from gplearn.genetic import _parallel_evolve, MAX_INT
from gplearn.genetic import BaseSymbolic

#==================================================================================================
# NUEVAS FUNCIONES
#==================================================================================================
#--------------------------------------------------------------------------------------------------
# Funciones generales
#--------------------------------------------------------------------------------------------------
# FUNCIÓN 1 (Calcular el error absoluto medio)
# Parámetros:
#   >z_test: terceras coordenadas reales de los puntos de la superficie.
#   >z_pred: terceras coordenadas obtenidas a partir de la superficie predicha.
# Devuelve: el error absoluto medio de las dos listas anteriores.
def mean_abs_err(z_test,z_pred):
    return sum(abs(z_test-z_pred))/len(z_test)

# FUNCIÓN 2 (Construir un conjunto de puntos extraído de una superficie)
# Parámetros:
#   >n_sample: número de puntos que se desean construir.
#   >seed: semilla para la selección aleatoria de los puntos.
#   >eval_expr: expresión de la superficie de la cual se quiere extraer la muestra de puntos.
# Devuelve: base de datos con las tres coordenadas de los puntos de la muestra.
def build_pts_sample(n_sample,seed,expr_surf):

    # Fijar la semilla.
    rng = check_random_state(seed)

    # Mallado aleatorio (x,y).
    xy_sample=rng.uniform(-1, 1, n_sample*2).reshape(n_sample, 2)
    x=xy_sample[:,0]
    y=xy_sample[:,1]

    # Calcular alturas correspondientes (valor z).
    z_sample=eval(expr_surf)

    # Todos los datos en un array.
    pts_sample=np.insert(xy_sample, xy_sample.shape[1], z_sample, 1)

    return pts_sample

# FUNCIÓN 3 ( Calcular el error absoluto medio de una conjunto de puntos respecto una superficie)
# Parámetros:
#   >df_test_pts: base de datos con las tres coordenadas de los puntos que forman el 
#    conjunto de validación.
#   >est_surf: superficie seleccionada en el proceso GA de entrenamiento.
# Devuelve: error absoluto medio.
def evaluate(df_test_pts,est_surf):

    # Dividir base de datos con las coordenadas de los puntos.
    xy_test=df_test_pts[:,[0,1]]
    z_test=df_test_pts[:,2]

    # Calcular el valor de las terceras coordenadas con las superficie seleccionada.
    z_pred=est_surf.predict(xy_test)

    # Calcular score asociado al conjunto de puntos para la superficie seleccionada.
    score=mean_abs_err(z_test, z_pred)

    return score   

# FUNCIÓN 4 ( Encontrar la expresión de la superficie que mejor se adapta a un conjunto de puntos inicial)
# Parámetros:
#   >init_acc: valor inicial del accuracy.
#   >default_train_n_pts: tamaño por defecto del conjunto de puntos de entrenamiento.
#   >train_pts_seed: semilla para construir el conjunto de puntos de entrenamiento.
#   >train_seed: semilla para definir la primera generación de superficies durante el proceso Symbolic Regressor.
#   >df_test_pts: conjunto de puntos de validación.
#   >max_n_eval: número máximo de evaluaciones definido para el proceso de búsqueda/entrenamiento de la superficie.
# Devuelve: expresión simbólica de la mejor superficie seleccionada durante el procedimiento.
def learn(init_acc,default_train_n_pts,train_pts_seed,train_seed,df_test_pts,max_n_eval,heuristic,heuristic_param):

    # Cambiar cardinal predefinido.
    train_n_pts=int(default_train_n_pts*init_acc)

    # Inicializar conjunto de entrenamiento.
    df_train_pts=build_pts_sample(train_n_pts,train_pts_seed,expr_surf_real)

    # Definición del algoritmo genético con el cual se encontrarán la superficie.
    est_surf=SymbolicRegressor(function_set= ('add', 'sub', 'mul', 'div','sqrt','log','abs','neg','inv','max','min','sin','cos','tan'),
                               verbose=0, random_state=train_seed)
    
    # Ajustar la superficie a los puntos.
    xy_train=df_train_pts[:,[0,1]]
    z_train=df_train_pts[:,2]
    est_surf.fit(init_acc,default_train_n_pts,train_pts_seed,xy_train, z_train,max_n_eval,train_seed,df_test_pts,heuristic,heuristic_param)    

    return est_surf._program 
#--------------------------------------------------------------------------------------------------
# Funciones para las heurísticas que definirán el accuracy ascendente
#--------------------------------------------------------------------------------------------------
# FUNCIÓN 5 (Cálculo del coeficiente de correlación de Spearman)
# Parámetros: x e y, los dos vectores sobre los cuales se desea calcular el coeficiente.
# Devuelve: coeficiente de correlación de Spearman.
def spearman_corr(x,y):
    return sc.stats.spearmanr(x,y)[0]

# FUNCIÓN 6 (Transformar lista de scores en ranking)
# Parámetros: list_scores, lista con los errores absolutos medios obtenidos al evaluar un conjunto de puntos 
# en cada una de las superficies que forman una generación.
# Devuelve: ranking asociado a la lista de scores.
def from_scores_to_ranking(list_scores):
    list_pos_ranking=np.argsort(np.array(list_scores))
    ranking=[0]*len(list_pos_ranking)
    i=0
    for j in list_pos_ranking:
        ranking[j]=i
        i+=1
    return ranking

# FUNCIÓN 7 (Evaluar un conjunto de puntos en cada superficie que forma una generación)
# Parámetros:
#   >list_surfaces: lista con las expresiones simbólicas de las superficies que forman una generación.
#   >df_pts: conjunto de puntos sobre los que se desean evaluar las superficies de la generación.
# Devuelve: lista de los scores (errores absolutos medios), uno por cada evaluación de una superficie 
# sobre el conjunto de puntos.
def generation_score_list(list_surfaces,df_pts):
    
    # Inicializar lista de scores.
    list_scores=[]

    # Dividir base de datos con las coordenadas de los puntos.
    X=df_pts[:,[0,1]]
    y=df_pts[:,2]

    # Evaluar cada superficie que forma la generación con el accuracy indicado.
    for expr_surf in list_surfaces:

        # Calcular el valor de las terceras coordenadas con las superficie seleccionada.
        y_pred=expr_surf.execute(X)

        # Calcular score asociado al conjunto de puntos para la superficie seleccionada.
        score=mean_abs_err(y, y_pred)

        # Añadir score a la lista.
        list_scores.append(score)

        # Contar una evaluación más en el contador general.
        global n_evaluations
        n_evaluations+=len(y)
     
    return list_scores

# FUNCIÓN 8 (Calculo del incremento de accuracy)
# Parámetros:
#   >p: valor de correlación de Spearman.
#   >acc_rest: valor de accuracy restante para alcanzar el máximo (=1).
# Devuelve: incremento de accuracy que se debe considerar según el p y el acc_rest introducidos.
def acc_split(corr,acc_rest,param):
    if param=='logistic':
        split=(1/(1+np.exp(12*(corr-0.5))))*acc_rest
    else:
        if corr<=param[0]:
            split=acc_rest
        else:
            split=-acc_rest*(((corr-param[0])/(1-param[0]))**(1/param[1]))+acc_rest
    return split

#__________________________________________________________________________________________________
# HEURÍSTICA 1: 

# FUNCIÓN 9
# Valoración de ascendencia de accuracy: correlación entre rankings (accuracy actual y máximo) del 10% aleatorio de superficies de la generación. 
# Definición de ascendencia de accuracy: función dependiente de la correlación anterior.
def acendant_acc_heuristic1(acc,population,fitness,default_train_n_pts,train_pts_seed,train_seed,expr_surf_real,param):
 
    # Seleccionar de forma aleatoria el 10% de las superficies que forman la generación.
    random.seed(train_seed)
    ind_surf=random.sample(range(len(population)),int(len(population)*0.1))
    list_surfaces=list(np.array(population)[ind_surf])

    # Guardar los scores asociados a cada superficie seleccionada.
    default_df_train_pts=build_pts_sample(default_train_n_pts,train_pts_seed,expr_surf_real)
    best_scores=generation_score_list(list_surfaces,default_df_train_pts)# Con el máximo accuracy. 
    current_scores=list(np.array(fitness)[ind_surf])# Accuracy actual.

    # Obtener vectores de rankings asociados.
    current_ranking=from_scores_to_ranking(current_scores)# Accuracy actual. 
    best_ranking=from_scores_to_ranking(best_scores)# Máximo accuracy. 
            
    # Comparar ambos rankings (calcular coeficiente de correlación de Spearman).
    corr=spearman_corr(current_ranking,best_ranking)

    # Dependiendo de la similitud entre los rankings calcular el split en el accuracy para la siguiente generación.
    split=acc_split(corr,1-acc,param)

    # Modificar accuracy .
    acc=acc+split

    # Calcular nuevo conjunto de entrenamiento.
    train_n_pts=int(default_train_n_pts*acc)
    df_train_pts=build_pts_sample(train_n_pts,train_pts_seed,expr_surf_real)
    X=df_train_pts[:,[0,1]]
    y=df_train_pts[:,2]

    return acc,X,y

#__________________________________________________________________________________________________
# HEURÍSTICA 2: 

# FUNCIÓN 10
# Valoración de ascendencia de accuracy: correlación entre rankings (accuracy actual y siguientes) del 10% aleatorio de superficies de la generación. 
# Definición de ascendencia de accuracy: siguiente accuracy en una lista predefinida (accuracys ascendentes exponencialmente).
def acendant_acc_heuristic2(acc,init_acc,population,fitness,default_train_n_pts,train_pts_seed,train_seed,expr_surf_real,param):
    # Definir lista de posibles accuracys que se van a considerar (valores exponenciales).
    list_acc=[init_acc]
    next_acc=list_acc[-1]*2
    while next_acc<1:
        list_acc.append(next_acc)
        next_acc=list_acc[-1]*2
    if 1 not in list_acc:
        list_acc.append(1)
 
    # Seleccionar de forma aleatoria el 10% de las superficies que forman la generación.
    random.seed(train_seed)
    ind_surf=random.sample(range(len(population)),int(len(population)*0.1))
    list_surfaces=list(np.array(population)[ind_surf])

    # Guardar los scores asociados a cada superficie seleccionada y calcular el ranking con el 
    # accuracy actual.
    current_scores=list(np.array(fitness)[ind_surf])
    current_ranking=from_scores_to_ranking(current_scores)

    # Mientras la correlación del ranking actual con el ranking asociado a un accuracy mayor no 
    # sea inferior al umbral seguir probando con el resto de accuracys.
    possible_acc=list(np.array(list_acc)[np.array(list_acc)>acc])
    ind_next_acc=0
    corr=1
    while corr>param and ind_next_acc<len(possible_acc):

        # Nuevo conjunto de puntos para evaluar las superficies.
        next_train_n_pts=int(default_train_n_pts*possible_acc[ind_next_acc])
        next_df_train_pts=build_pts_sample(next_train_n_pts,train_pts_seed,expr_surf_real)

        # Guardar scores de las superficies seleccionadas calculados con el accuracy siguiente y
        # obtener el ranking correspondiente.
        next_scores=generation_score_list(list_surfaces,next_df_train_pts)
        next_ranking=from_scores_to_ranking(next_scores)

        # Comparar ambos rankings (calcular coeficiente de correlación de Spearman).
        corr=spearman_corr(current_ranking,next_ranking)
        # Actualización de indice de accuracy.
        ind_next_acc+=1
    
    # Modificar accuracy.
    if corr<param:
        #acc=possible_acc[ind_next_acc-1]
        acc=possible_acc[0]
    
    # Calcular nuevo conjunto de entrenamiento.
    train_n_pts=int(default_train_n_pts*acc)
    df_train_pts=build_pts_sample(train_n_pts,train_pts_seed,expr_surf_real)
    X=df_train_pts[:,[0,1]]
    y=df_train_pts[:,2]

    return acc,X,y

#__________________________________________________________________________________________________
# HEURÍSTICA 3: 

# FUNCIÓN 11
# Valoración de ascendencia de accuracy: correlación entre rankings (accuracy mínimo y actual) de superficies de la generación. 
# Definición de ascendencia de accuracy: siguiente accuracy en una lista predefinida (accuracys ascendentes exponencialmente).
def acendant_acc_heuristic3(acc,init_acc,population,fitness,default_train_n_pts,train_pts_seed,expr_surf_real,param):
    # Definir lista de posibles accuracys que se van a considerar (valores exponenciales).
    list_acc=[init_acc]
    next_acc=list_acc[-1]*2
    while next_acc<1:
        list_acc.append(next_acc)
        next_acc=list_acc[-1]*2
    if 1 not in list_acc:
        list_acc.append(1)
    possible_acc=list(np.array(list_acc)[np.array(list_acc)>acc])

    # Guardar los scores asociados a cada superficie.
    list_surfaces=list(population)
    worst_df_train_pts=build_pts_sample(int(default_train_n_pts*init_acc),train_pts_seed,expr_surf_real)
    worst_scores=generation_score_list(list_surfaces,worst_df_train_pts)# Con el mínimo accuracy. 
    current_scores=fitness# Accuracy actual.
    
    # Obtener vectores de rankings asociados.
    current_ranking=from_scores_to_ranking(current_scores)# Accuracy actual. 
    worst_ranking=from_scores_to_ranking(worst_scores)# Mínimo accuracy. 
            
    # Comparar ambos rankings (calcular coeficiente de correlación de Spearman).
    corr=spearman_corr(current_ranking,worst_ranking)

    # Dependiendo de la similitud entre los rankings considerar un accuracy mayor para la siguiente generación.
    if corr>param:
        acc=possible_acc[0]

    # Calcular nuevo conjunto de entrenamiento.
    train_n_pts=int(default_train_n_pts*acc)
    df_train_pts=build_pts_sample(train_n_pts,train_pts_seed,expr_surf_real)
    X=df_train_pts[:,[0,1]]
    y=df_train_pts[:,2]

    return acc,X,y


#__________________________________________________________________________________________________
# HEURÍSTICA 4: NO CONSIDERAR

# FUNCIÓN 12
# Valoración de ascendencia de accuracy: correlación entre rankings (accuracy actual y máximo) del 10% mejor de superficies de la generación. 
# Definición de ascendencia de accuracy: función dependiente de la correlación anterior.
def acendant_acc_heuristic4(acc,population,fitness,default_train_n_pts,train_pts_seed,expr_surf_real,param):

    # Obtener el ranking de los scores asociados a cada superficie seleccionada calculados con el accuracy actual.
    list_surfaces=list(population)
    all_current_ranking=from_scores_to_ranking(fitness)

    # Reducir el conjunto de superficies al 10% inicial según el ranking anterior.
    for ranking_pos in range(int(len(population)*0.1),len(population)):
        # Eliminar posiciones y superficies que no se usarán.
        ind_remove=all_current_ranking.index(ranking_pos)
        all_current_ranking.remove(ranking_pos)
        list_surfaces.pop(ind_remove)
    current_ranking=all_current_ranking

    # Guardar scores de las superficies seleccionadas calculados con el accuracy máximo y
    # obtener el ranking correspondiente.
    best_df_train_pts=build_pts_sample(default_train_n_pts,train_pts_seed,expr_surf_real)
    best_scores=generation_score_list(list_surfaces,best_df_train_pts)# Con el máximo accuracy. 
    best_ranking=from_scores_to_ranking(best_scores)# Máximo accuracy. 
            
    # Comparar ambos rankings (calcular coeficiente de correlación de Spearman).
    corr=spearman_corr(current_ranking,best_ranking)

    # Dependiendo de la similitud entre los rankings calcular el split en el accuracy para la siguiente generación.
    split=acc_split(corr,1-acc,param)

    # Modificar accuracy .
    acc=acc+split

    # Calcular nuevo conjunto de entrenamiento.
    train_n_pts=int(default_train_n_pts*acc)
    df_train_pts=build_pts_sample(train_n_pts,train_pts_seed,expr_surf_real)
    X=df_train_pts[:,[0,1]]
    y=df_train_pts[:,2]

    return acc,X,y

#__________________________________________________________________________________________________
# HEURÍSTICA 5: NO CONSIDERAR

# FUNCIÓN 13
# Valoración de ascendencia de accuracy: correlación entre rankings (accuracy actual y siguientes) del 10% mejor de superficies de la generación. 
# Definición de ascendencia de accuracy: siguiente accuracy en una lista predefinida (accuracys ascendentes exponencialmente).
def acendant_acc_heuristic5(acc,init_acc,population,fitness,default_train_n_pts,train_pts_seed,expr_surf_real,param):
    # Definir lista de posibles accuracys que se van a considerar (valores exponenciales).
    list_acc=[init_acc]
    next_acc=list_acc[-1]*2
    while next_acc<1:
        list_acc.append(next_acc)
        next_acc=list_acc[-1]*2
    if 1 not in list_acc:
        list_acc.append(1)
 
    # Guardar los scores asociados a cada superficie seleccionada calculados con el accuracy actual y
    # obtener el correspondiente ranking.
    all_current_ranking=from_scores_to_ranking(fitness)

    # Reducir el conjunto de superficies al 10% inicial según el ranking anterior.
    list_surfaces=list(population)
    for ranking_pos in range(int(len(population)*0.1),len(population)):
        # Eliminar posiciones y superficies que no se usarán.
        ind_remove=all_current_ranking.index(ranking_pos)
        all_current_ranking.remove(ranking_pos)
        list_surfaces.pop(ind_remove)
    current_ranking=all_current_ranking

    # Mientras la correlación del ranking actual con el ranking asociado a un accuracy mayor no 
    # sea inferior al umbral seguir probando con el resto de accuracys.
    possible_acc=list(np.array(list_acc)[np.array(list_acc)>acc])
    ind_next_acc=0
    corr=1
    while corr>param and ind_next_acc<len(possible_acc):

        # Nuevo conjunto de puntos para evaluar las superficies.
        next_train_n_pts=int(default_train_n_pts*possible_acc[ind_next_acc])
        next_df_train_pts=build_pts_sample(next_train_n_pts,train_pts_seed,expr_surf_real)

        # Guardar scores de las superficies seleccionadas calculados con el accuracy siguiente y
        # obtener el ranking correspondiente.
        next_scores=generation_score_list(list_surfaces,next_df_train_pts)
        next_ranking=from_scores_to_ranking(next_scores)

        # Comparar ambos rankings (calcular coeficiente de correlación de Spearman).
        corr=spearman_corr(current_ranking,next_ranking)

        # Actualización de indice de accuracy.
        ind_next_acc+=1
    
    # Modificar accuracy.
    if corr<param:
        #acc=possible_acc[ind_next_acc-1]
        acc=possible_acc[0]
    
    # Calcular nuevo conjunto de entrenamiento.
    train_n_pts=int(default_train_n_pts*acc)
    df_train_pts=build_pts_sample(train_n_pts,train_pts_seed,expr_surf_real)
    X=df_train_pts[:,[0,1]]
    y=df_train_pts[:,2]

    return acc,X,y

#==================================================================================================
# FUNCIONES DISEÑADAS A PARTIR DE ALGUNAS YA EXISTENTES
#==================================================================================================

# FUNCIÓN 11
# -Original: raw_fitness
# -Script: _Program.py
# -Clase: _Program
def new_raw_fitness(self, X, y, sample_weight):
    
    y_pred = self.execute(X)
    if self.transformer:
        y_pred = self.transformer(y_pred)
    raw_fitness = self.metric(y, y_pred, sample_weight)
    
    # MODIFICACIÓN: Sumar el número de evaluaciones realizadas (tantas como puntos en el 
    # conjunto de entrenamiento).
    global n_evaluations
    n_evaluations+=X.shape[0]

    return raw_fitness

# FUNCIÓN 12
# -Original: _parallel_evolve
# -Script: genetic.py
def new_parallel_evolve(n_programs, parents, X, y, sample_weight, seeds, params):
   
    n_samples, n_features = X.shape
    # Unpack parameters
    tournament_size = params['tournament_size']
    function_set = params['function_set']
    arities = params['arities']
    init_depth = params['init_depth']
    init_method = params['init_method']
    const_range = params['const_range']
    metric = params['_metric']
    transformer = params['_transformer']
    parsimony_coefficient = params['parsimony_coefficient']
    method_probs = params['method_probs']
    p_point_replace = params['p_point_replace']
    max_samples = params['max_samples']
    feature_names = params['feature_names']

    max_samples = int(max_samples * n_samples)

    def _tournament():
        """Find the fittest individual from a sub-population."""
        contenders = random_state.randint(0, len(parents), tournament_size)
        fitness = [parents[p].fitness_ for p in contenders]
        if metric.greater_is_better:
            parent_index = contenders[np.argmax(fitness)]
        else:
            parent_index = contenders[np.argmin(fitness)]
        return parents[parent_index], parent_index

    # Build programs
    programs = []
    i=0# MODIFICACIÓN: inicializar contador de forma manual.
    while i<n_programs and n_evaluations<max_n_eval:#MODIFICACIÓN: añadir nueva restricción para terminar el bucle.

        random_state = check_random_state(seeds[i])

        if parents is None:
            program = None
            genome = None
        else:
            method = random_state.uniform()
            parent, parent_index = _tournament()

            if method < method_probs[0]:
                # crossover
                donor, donor_index = _tournament()
                program, removed, remains = parent.crossover(donor.program,
                                                             random_state)
                genome = {'method': 'Crossover',
                          'parent_idx': parent_index,
                          'parent_nodes': removed,
                          'donor_idx': donor_index,
                          'donor_nodes': remains}
            elif method < method_probs[1]:
                # subtree_mutation
                program, removed, _ = parent.subtree_mutation(random_state)
                genome = {'method': 'Subtree Mutation',
                          'parent_idx': parent_index,
                          'parent_nodes': removed}
            elif method < method_probs[2]:
                # hoist_mutation
                program, removed = parent.hoist_mutation(random_state)
                genome = {'method': 'Hoist Mutation',
                          'parent_idx': parent_index,
                          'parent_nodes': removed}
            elif method < method_probs[3]:
                # point_mutation
                program, mutated = parent.point_mutation(random_state)
                genome = {'method': 'Point Mutation',
                          'parent_idx': parent_index,
                          'parent_nodes': mutated}
            else:
                # reproduction
                program = parent.reproduce()
                genome = {'method': 'Reproduction',
                          'parent_idx': parent_index,
                          'parent_nodes': []}

        program = _Program(function_set=function_set,
                           arities=arities,
                           init_depth=init_depth,
                           init_method=init_method,
                           n_features=n_features,
                           metric=metric,
                           transformer=transformer,
                           const_range=const_range,
                           p_point_replace=p_point_replace,
                           parsimony_coefficient=parsimony_coefficient,
                           feature_names=feature_names,
                           random_state=random_state,
                           program=program)

        program.parents = genome

        # Draw samples, using sample weights, and then fit
        if sample_weight is None:
            curr_sample_weight = np.ones((n_samples,))
        else:
            curr_sample_weight = sample_weight.copy()
        oob_sample_weight = curr_sample_weight.copy()

        indices, not_indices = program.get_all_indices(n_samples,
                                                       max_samples,
                                                       random_state)

        curr_sample_weight[not_indices] = 0
        oob_sample_weight[indices] = 0

        
        
        program.raw_fitness_=program.raw_fitness(X, y, curr_sample_weight)
         
        if max_samples < n_samples:
            # Calculate OOB fitness
            program.oob_fitness_= program.raw_fitness(X, y, oob_sample_weight)
            

        programs.append(program)

        i+=1# MODIFICACIÓN: actualizar contador de forma manual.
    return programs

# FUNCIÓN 13
# Esta función contiene una parte del código interno de una función ya existente.
# -Original: fit
# -Script: genetic.py 
def find_best_individual_final_generation(self,fitness):

    if isinstance(self, TransformerMixin):
        # Find the best individuals in the final generation
        fitness = np.array(fitness)
        if self._metric.greater_is_better:
            hall_of_fame = fitness.argsort()[::-1][:self.hall_of_fame]
        else:
            hall_of_fame = fitness.argsort()[:self.hall_of_fame]
        evaluation = np.array([gp.execute(X) for gp in
                                [self._programs[-1][i] for
                                i in hall_of_fame]])
        if self.metric == 'spearman':
            evaluation = np.apply_along_axis(rankdata, 1, evaluation)

        with np.errstate(divide='ignore', invalid='ignore'):
            correlations = np.abs(np.corrcoef(evaluation))
        np.fill_diagonal(correlations, 0.)
        components = list(range(self.hall_of_fame))
        indices = list(range(self.hall_of_fame))
        # Iteratively remove least fit individual of most correlated pair
        while len(components) > self.n_components:
            most_correlated = np.unravel_index(np.argmax(correlations),
                                                correlations.shape)
            # The correlation matrix is sorted by fitness, so identifying
            # the least fit of the pair is simply getting the higher index
            worst = max(most_correlated)
            components.pop(worst)
            indices.remove(worst)
            correlations = correlations[:, indices][indices, :]
            indices = list(range(len(components)))
        self._best_programs = [self._programs[-1][i] for i in
                                hall_of_fame[components]]

    else:
        # Find the best individual in the final generation
        if self._metric.greater_is_better:
            self._program = self._programs[-1][np.argmax(fitness)]
        else:
            self._program = self._programs[-1][np.argmin(fitness)]

# FUNCIÓN 14
# -Original: fit
# -Script: genetic.py
# -Clase: BaseSymbolic
def new_fit(self,init_acc,default_train_n_pts,train_pts_seed, X, y, max_n_eval, train_seed,df_test_pts,heuristic,heuristic_param,sample_weight=None):# MODIFICACIÓN: añadir nuevos argumentos.

    random_state = check_random_state(self.random_state)

    # Check arrays
    if sample_weight is not None:
        sample_weight = _check_sample_weight(sample_weight, X)

    if isinstance(self, ClassifierMixin):
        X, y = self._validate_data(X, y, y_numeric=False)
        check_classification_targets(y)

        if self.class_weight:
            if sample_weight is None:
                sample_weight = 1.
            # modify the sample weights with the corresponding class weight
            sample_weight = (sample_weight *
                                compute_sample_weight(self.class_weight, y))

        self.classes_, y = np.unique(y, return_inverse=True)
        n_trim_classes = np.count_nonzero(np.bincount(y, sample_weight))
        if n_trim_classes != 2:
            raise ValueError("y contains %d class after sample_weight "
                                "trimmed classes with zero weights, while 2 "
                                "classes are required."
                                % n_trim_classes)
        self.n_classes_ = len(self.classes_)

    else:
        X, y = self._validate_data(X, y, y_numeric=True)

    hall_of_fame = self.hall_of_fame
    if hall_of_fame is None:
        hall_of_fame = self.population_size
    if hall_of_fame > self.population_size or hall_of_fame < 1:
        raise ValueError('hall_of_fame (%d) must be less than or equal to '
                            'population_size (%d).' % (self.hall_of_fame,
                                                    self.population_size))
    n_components = self.n_components
    if n_components is None:
        n_components = hall_of_fame
    if n_components > hall_of_fame or n_components < 1:
        raise ValueError('n_components (%d) must be less than or equal to '
                            'hall_of_fame (%d).' % (self.n_components,
                                                    self.hall_of_fame))

    self._function_set = []
    for function in self.function_set:
        if isinstance(function, str):
            if function not in _function_map:
                raise ValueError('invalid function name %s found in '
                                    '`function_set`.' % function)
            self._function_set.append(_function_map[function])
        elif isinstance(function, _Function):
            self._function_set.append(function)
        else:
            raise ValueError('invalid type %s found in `function_set`.'
                                % type(function))
    if not self._function_set:
        raise ValueError('No valid functions found in `function_set`.')

    # For point-mutation to find a compatible replacement node
    self._arities = {}
    for function in self._function_set:
        arity = function.arity
        self._arities[arity] = self._arities.get(arity, [])
        self._arities[arity].append(function)

    if isinstance(self.metric, _Fitness):
        self._metric = self.metric
    elif isinstance(self, RegressorMixin):
        if self.metric not in ('mean absolute error', 'mse', 'rmse',
                                'spearman', 'spearman'):
            raise ValueError('Unsupported metric: %s' % self.metric)
        self._metric = _fitness_map[self.metric]
    elif isinstance(self, ClassifierMixin):
        if self.metric != 'log loss':
            raise ValueError('Unsupported metric: %s' % self.metric)
        self._metric = _fitness_map[self.metric]
    elif isinstance(self, TransformerMixin):
        if self.metric not in ('spearman', 'spearman'):
            raise ValueError('Unsupported metric: %s' % self.metric)
        self._metric = _fitness_map[self.metric]

    self._method_probs = np.array([self.p_crossover,
                                    self.p_subtree_mutation,
                                    self.p_hoist_mutation,
                                    self.p_point_mutation])
    self._method_probs = np.cumsum(self._method_probs)

    if self._method_probs[-1] > 1:
        raise ValueError('The sum of p_crossover, p_subtree_mutation, '
                            'p_hoist_mutation and p_point_mutation should '
                            'total to 1.0 or less.')

    if self.init_method not in ('half and half', 'grow', 'full'):
        raise ValueError('Valid program initializations methods include '
                            '"grow", "full" and "half and half". Given %s.'
                            % self.init_method)

    if not((isinstance(self.const_range, tuple) and
            len(self.const_range) == 2) or self.const_range is None):
        raise ValueError('const_range should be a tuple with length two, '
                            'or None.')

    if (not isinstance(self.init_depth, tuple) or
            len(self.init_depth) != 2):
        raise ValueError('init_depth should be a tuple with length two.')
    if self.init_depth[0] > self.init_depth[1]:
        raise ValueError('init_depth should be in increasing numerical '
                            'order: (min_depth, max_depth).')

    if self.feature_names is not None:
        if self.n_features_in_ != len(self.feature_names):
            raise ValueError('The supplied `feature_names` has different '
                                'length to n_features. Expected %d, got %d.'
                                % (self.n_features_in_,
                                len(self.feature_names)))
        for feature_name in self.feature_names:
            if not isinstance(feature_name, str):
                raise ValueError('invalid type %s found in '
                                    '`feature_names`.' % type(feature_name))

    if self.transformer is not None:
        if isinstance(self.transformer, _Function):
            self._transformer = self.transformer
        elif self.transformer == 'sigmoid':
            self._transformer = sigmoid
        else:
            raise ValueError('Invalid `transformer`. Expected either '
                                '"sigmoid" or _Function object, got %s' %
                                type(self.transformer))
        if self._transformer.arity != 1:
            raise ValueError('Invalid arity for `transformer`. Expected 1, '
                                'got %d.' % (self._transformer.arity))

    params = self.get_params()
    params['_metric'] = self._metric
    if hasattr(self, '_transformer'):
        params['_transformer'] = self._transformer
    else:
        params['_transformer'] = None
    params['function_set'] = self._function_set
    params['arities'] = self._arities
    params['method_probs'] = self._method_probs

    if not self.warm_start or not hasattr(self, '_programs'):
        # Free allocated memory, if any
        self._programs = []
        self.run_details_ = {'generation': [],
                                'average_length': [],
                                'average_fitness': [],
                                'best_length': [],
                                'best_fitness': [],
                                'best_oob_fitness': [],
                                'generation_time': []}

    prior_generations = len(self._programs)
    n_more_generations = self.generations - prior_generations

    if n_more_generations < 0:
        raise ValueError('generations=%d must be larger or equal to '
                            'len(_programs)=%d when warm_start==True'
                            % (self.generations, len(self._programs)))
    elif n_more_generations == 0:
        fitness = [program.raw_fitness_ for program in self._programs[-1]]
        warn('Warm-start fitting without increasing n_estimators does not '
                'fit new programs.')

    if self.warm_start:
        # Generate and discard seeds that would have been produced on the
        # initial fit call.
        for i in range(len(self._programs)):
            _ = random_state.randint(MAX_INT, size=self.population_size)

    if self.verbose:
        # Print header fields
        self._verbose_reporter()

    start_total_time=time() #MODIFICACIÓN: empezar a contar el tiempo de entrenamiento.
    gen=0# MODIFICACIÓN: para que el procedimiento no termine cuando se alcance un número de generaciones, las generaciones se cuentan con un contador independiente.
    
    # MODIFICACIÓN: variable global mediante la cual se irán contando el número de evaluaciones realizadas,
    # entendiendo por evaluación cada evaluación de un punto en una expresión de una superficie.
    global n_evaluations
    n_evaluations=0
    acc=init_acc
    while n_evaluations < max_n_eval:# MODIFICACIÓN: modificar el límite de entrenamiento.

        start_time = time()

        if gen == 0:
            parents = None
        else:
            parents = self._programs[gen - 1]

        # Parallel loop
        n_jobs, n_programs, starts = _partition_estimators(
            self.population_size, self.n_jobs)
        seeds = random_state.randint(MAX_INT, size=self.population_size)

        population = Parallel(n_jobs=n_jobs,
                                verbose=int(self.verbose > 1))(
            delayed(_parallel_evolve)(n_programs[i],
                                        parents,
                                        X,
                                        y,
                                        sample_weight,
                                        seeds[starts[i]:starts[i + 1]],
                                        params)
            for i in range(n_jobs))

        # Reduce, maintaining order across different n_jobs
        population = list(itertools.chain.from_iterable(population))

        fitness = [program.raw_fitness_ for program in population]
        length = [program.length_ for program in population]

        parsimony_coefficient = None
        if self.parsimony_coefficient == 'auto':
            parsimony_coefficient = (np.cov(length, fitness)[1, 0] /
                                        np.var(length))
        for program in population:
            program.fitness_ = program.fitness(parsimony_coefficient)

        self._programs.append(population)

        # Remove old programs that didn't make it into the new population.
        if not self.low_memory:
            for old_gen in np.arange(gen, 0, -1):
                indices = []
                for program in self._programs[old_gen]:
                    if program is not None:
                        for idx in program.parents:
                            if 'idx' in idx:
                                indices.append(program.parents[idx])
                indices = set(indices)
                for idx in range(self.population_size):
                    if idx not in indices:
                        self._programs[old_gen - 1][idx] = None
        elif gen > 0:
            # Remove old generations
            self._programs[gen - 1] = None

        # Record run details
        if self._metric.greater_is_better:
            best_program = population[np.argmax(fitness)]
        else:
            best_program = population[np.argmin(fitness)]

        self.run_details_['generation'].append(gen)
        self.run_details_['average_length'].append(np.mean(length))
        self.run_details_['average_fitness'].append(np.mean(fitness))
        self.run_details_['best_length'].append(best_program.length_)
        self.run_details_['best_fitness'].append(best_program.raw_fitness_)
        oob_fitness = np.nan
        if self.max_samples < 1.0:
            oob_fitness = best_program.oob_fitness_
        self.run_details_['best_oob_fitness'].append(oob_fitness)
        generation_time = time() - start_time
        self.run_details_['generation_time'].append(generation_time)

        if self.verbose:
            self._verbose_reporter(self.run_details_)

        # Check for early stopping
        if self._metric.greater_is_better:
            best_fitness = fitness[np.argmax(fitness)]
        else:
            best_fitness = fitness[np.argmin(fitness)]
        

        find_best_individual_final_generation(self,fitness) # MODIFICACIÓN: para poder evaluar la mejor superficie durante el proceso.
        
        # MODIFICACIÓN: ir guardando los datos de interés durante el entrenamiento. 
        score=evaluate(df_test_pts,self)
        elapsed_time=time()-start_total_time   
        df_train.append([train_seed,acc,gen,score,elapsed_time,generation_time,n_evaluations,heuristic_param])

        # MODIFICACIÓN: modificación automática del accuracy y el conjunto de entrenamiento.
        if acc<1:
            if heuristic==1:
                acc,X,y=acendant_acc_heuristic1(acc,population,fitness,default_train_n_pts,train_pts_seed,train_seed,expr_surf_real,heuristic_param)
            if heuristic==2:
                acc,X,y=acendant_acc_heuristic2(acc,init_acc,population,fitness,default_train_n_pts,train_pts_seed,train_seed,expr_surf_real,heuristic_param)
            if heuristic==3:
                acc,X,y=acendant_acc_heuristic3(acc,init_acc,population,fitness,default_train_n_pts,train_pts_seed,expr_surf_real,heuristic_param)
            if heuristic==4:
                acc,X,y=acendant_acc_heuristic4(acc,population,fitness,default_train_n_pts,train_pts_seed,expr_surf_real,heuristic_param)
            if heuristic==5:
                acc,X,y=acendant_acc_heuristic5(acc,init_acc,population,fitness,default_train_n_pts,train_pts_seed,expr_surf_real,heuristic_param)
            
        gen+=1# MODIFICACIÓN: actualizar número de generaciones.

    find_best_individual_final_generation(self,fitness)# MODIFICACIÓN: para obtener el mejor individuo de la última generación.
    
    return self

#==================================================================================================
# PROGRAMA PRINCIPAL
#==================================================================================================
# Para usar la función de ajuste modificada.
_Program.raw_fitness=new_raw_fitness
_parallel_evolve=new_parallel_evolve
BaseSymbolic.fit=new_fit

# Superficie.
expr_surf_real='x**2-y**2+y-1'

# Mallados.
list_train_seeds=range(1,31,1)# Semillas de entrenamiento.
list_heuristics=[1,2,3]# Tipos de heurísticas.

# Parámetros de heurísticas.
list_param1=['logistic']#[(0,1),(0,3),(0.5,3),(0.5,1),(0,0.3)] # (>=1)Potencia de raíz que define la función que fijara el split del accuracy para la siguiente generación en la (heurística 1 y 2).
list_param2=[0.8,0.6]# (en (-1,1))Umbral de correlación de Spearman para detectar si la clasificación actual puede ser mala (heurística 3 y 4).
list_param3=[0.6]# Umbral de correlación de Spearman para detectar si la clasificación actual puede ser mala (herística 5)
heuristic_params=[list_param1,list_param2,list_param3]

# Parámetros de entrenamiento.
default_train_n_pts=50# Cardinal de conjunto inicial predefinido.
train_pts_seed=0
max_n_eval=10000000

# Parámetros y conjunto de validación.
test_n_pts=default_train_n_pts
test_pts_seed=1
df_test_pts=build_pts_sample(test_n_pts,test_pts_seed,expr_surf_real)

# Accuracy de partida (el correspondiente a un conjunto inicial de 3 puntos).
init_acc=3/default_train_n_pts

# Guardar datos de entrenamiento.
for heuristic in list_heuristics:
    df_train=[]
    if heuristic in [1,4]:
        list_params=heuristic_params[0]
    if heuristic in [2,5]:
        list_params=heuristic_params[1]
    if heuristic==3:
        list_params=heuristic_params[2]
    for heuristic_param in list_params:
        for train_seed in tqdm(list_train_seeds):
            #Entrenamiento.
            expr_surf_pred=learn(init_acc,default_train_n_pts,train_pts_seed,train_seed,df_test_pts,max_n_eval,heuristic,heuristic_param)

    df_train=pd.DataFrame(df_train,columns=['train_seed','acc','n_gen','score','elapsed_time','time_gen','n_eval','heuristic_param'])
    df_train.to_csv('results/data/SymbolicRegressor/df_train_AscendantAccuracy_heuristic'+str(heuristic)+'_.csv')

# Guardar expresión de superficie.
np.save('results/data/SymbolicRegressor/expr_surf',expr_surf_real)

# Guardar lista de heurísticas.
np.save('results/data/SymbolicRegressor/list_heuristics',list_heuristics)




