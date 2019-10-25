import pandas as pd
from pandas.tools.plotting import scatter_matrix
import numpy as np
import scipy.stats as stats
import matplotlib.pyplot as plt
from itertools import product
import math

from .expression import Expression, Var, Quantitative, Categorical, Interaction, Combination, Identity, Constant

plt.style.use('ggplot')

class Model:
    ''' A general Model class that both Linear models and (in the future) General Linear models stem from. '''

    def __init__(self):
        ''' Create a Model object (only possible through inheritance). '''
        raise NotImplementedError()
        
    def fit(self, data):
        ''' Fit a model to given data.

        Arguments:
            data - A DataFrame with column names matching specified terms within the Model's explanatory and response Expression objects.

        Returns:
            A DataFrame object with relevant statistics of fitted Model (coefficients, t statistics, p-values, etc.).
        '''
        raise NotImplementedError()
        
    def predict(self, data):
        ''' Predict response values for a given set of data.

        Arguments:
            data - A DataFrame with column names matching specified terms within the Model's explanatory Expression object.
        
        Returns:    
            A Series object of the predicted values.
        '''
        raise NotImplementedError()
        
    def plot_matrix(self, **kwargs):
        ''' Produce a matrix of pairwise scatter plots of the data it was fit on. The diagonal of the matrix will feature
        histograms instead of scatter plots.

        Arguments:
            kwargs - One or more named parameters that will be ingested by Pandas' scatter_matrix plotting function.
        
        Returns:
            A matplotlib plot object containing the matrix of scatter plots. 
        '''         
        df = pd.concat([self.training_x, self.training_y], axis = 1)
        scatter_matrix(df, **kwargs)
    
    
class LinearModel(Model):
    ''' A specific kind of Model that assumes the response values are in a linearl relationship with the explantory variables. '''

    def __init__(self, explanatory, response, intercept = True):
        ''' Create a LinearModel object. 
        If an intercept is not wanted, can either set intercept = False or subtract '1' from the explanatory Expression.

        Arguments:
            explanatory - An Expression object that is either a single term or a Combination of them. These are the X's.
            response - An Expression object that represents the single term for the response variables. This is the Y. 
                If this is a Combination, they will be added together and treated as a single variable.
            intercept - A boolean that indicates if an intercept is wanted (True) or not (False).
        '''

        if isinstance(explanatory, (int, float)):
            explanatory = Constant(explanatory)

        if intercept:
            self.given_ex = explanatory + 1
        else:
            self.given_ex = explanatory    
        constant = self.given_ex.reduce()['Constant']
        self.intercept = constant is not None
        if self.intercept:
            self.given_ex = self.given_ex - constant # This was done to easily check all options for indicating a wanted intercept
                
        self.given_re = Identity(response) # This will collapse any combination of variables into a single column
        self.ex = None
        self.re = None
        self.bhat = None
        self.fitted = None
        self.residuals = None
        self.std_err_est = None
        self.std_err_vars = None
        self.var = None
        self.t_vals = None
        self.p_vals = None
        self.training_data = None
        self.training_x = None
        self.training_y = None
        self.categorical_levels = dict()
        
    def __str__(self):
        ''' Convert a LinearModel to a str format for printing. '''
        if self.intercept:
            return str(self.given_re) + " ~ " + str(1 + self.given_ex)
        else:
            return str(self.given_re) + " ~ " + str(self.given_ex)

    def fit(self, X, Y = None):
        ''' Exposed function for fitting a LinearModel. Can either give one DataFrame that contains both
        response and explanatory variables or separate ones. This is done to interface into the sklearn ecosystem.

        It is worth noting that it is fine to have extra columns that are not used by the model - they will just be ignored.

        Arugments:
            X - A DataFrame object that contains either the response and explanatory data, or just the explanatory data. 
            Y - An optional DataFrame object that contains the response data.

        Returns:
            A DataFrame object with relevant statistics of fitted Model (coefficients, t statistics, p-values, etc.).
        '''
        if Y is None:
            data = X
        else:
            data = pd.concat([X,Y], axis = 1)
        return self._fit(data)

    def _fit_intercept_only(self, data):
        # Construct X matrix
        self.ex = Constant(1)
        X = self.ex.evaluate(data)
        X.columns = ["Intercept"]
        self.training_x = X
        # Construct Y vector
        y = self.re.evaluate(data)
        y_mean = y.mean()
        self.training_y = y

        # Solve equation
        self.bhat = pd.DataFrame(np.linalg.solve(np.dot(X.T, X), np.dot(X.T, y)),
                                 index=X.columns, columns=["Coefficients"])

        n = X.shape[0]
        p = X.shape[1] - (1 if self.intercept else 0)

        # Y_Hat and Residuals
        self.fitted = pd.DataFrame({"Fitted": np.dot(X, self.bhat).sum(axis=1)})
        self.residuals = pd.DataFrame({"Residuals": y.iloc[:, 0] - self.fitted.iloc[:, 0]})

        # Sigma
        self.std_err_est = ((self.residuals["Residuals"] ** 2).sum() / (n - p - 1)) ** 0.5

        # Covariance Matrix
        self.var = np.linalg.solve(np.dot(X.T, X),
                                   (self.std_err_est ** 2) * np.identity(X.shape[1]))

        # Coefficient SE, Diagonal of Cov. Matrix
        self.std_err_vars = pd.DataFrame({"SE": (np.diagonal(self.var)) ** 0.5},
                                         index=self.bhat.index)

        # format the covariance matrix
        self.var = pd.DataFrame(self.var, columns=X.columns, index=X.columns)

        # Coefficient Inference
        self.t_vals = pd.DataFrame({"t": self.bhat["Coefficients"] / self.std_err_vars["SE"]})
        self.p_vals = pd.DataFrame({"p": pd.Series(2 * stats.t.cdf(-abs(self.t_vals["t"]), n - p - 1),
                                                   index=self.bhat.index)})

        ret_val = pd.concat([self.bhat, self.std_err_vars, self.t_vals, self.p_vals], axis=1)

        return ret_val
        
    def _fit(self, data):
        ''' Helper function for fitting a model with given data. 

        Arguments:
            data - A DataFrame object containing the explanatory and response columns (amongst potentially extraneous columns as well).

        Returns:
            A DataFrame object with relevant statistics of fitted Model (coefficients, t statistics, p-values, etc.).
        '''
        # Initialize the categorical levels
        self.categorical_levels = dict()
        self.training_data = data
        
        # Replace all Var's with either Q's or C's
        self.re = self.given_re.copy()
        self.re = self.re.interpret(data)       
        if self.given_ex == 0:
            return self._fit_intercept_only(data)

        self.ex = self.given_ex.copy()
        self.ex = self.ex.interpret(data)

        terms = self.ex.reduce()
        
        # Construct X matrix
        X = self.ex.evaluate(data)
        X_means = X.mean()
        self.training_x = X
        self.training_x_means = X_means
        # Construct Y vector
        y = self.re.evaluate(data)
        y_mean = y.mean()
        self.training_y = y
        self.training_y_mean = y_mean

        # Center if there is an intercept
        if self.intercept:
            X = X - X_means
            y = y - y_mean
        
        # Solve equation
        self.bhat = pd.DataFrame(np.linalg.solve(np.dot(X.T, X), np.dot(X.T, y)), 
                                 index=X.columns, columns=["Coefficients"])
        if self.intercept:
            self.bhat.loc["Intercept"] = [y_mean[0] - X_means.dot(self.bhat)[0]]
            X = X + X_means
            X['Intercept'] = 1
            y = y + y_mean
            
            
    
        n = X.shape[0]
        p = X.shape[1]

        # Y_Hat and Residuals
        self.fitted = pd.DataFrame({"Fitted" : np.dot(X, self.bhat).sum(axis = 1)})
        self.residuals = pd.DataFrame({"Residuals" : y.iloc[:,0] - self.fitted.iloc[:,0]})
        
        # Sigma Hat
        self.std_err_est = ((self.residuals["Residuals"] ** 2).sum() / (n - p)) ** 0.5

        # Covariance Matrix        
        self.var = np.linalg.solve(np.dot(X.T, X), 
                                   (self.std_err_est ** 2) * np.identity(X.shape[1]))

        # Coefficient SE, Diagonal of Cov. Matrix
        self.std_err_vars = pd.DataFrame({"SE": (np.diagonal(self.var)) ** 0.5},
                                         index=self.bhat.index)
        
        # format the covariance matrix
        self.var = pd.DataFrame(self.var, columns=X.columns, index=X.columns)
        
        # Coefficient Inference
        self.t_vals = pd.DataFrame({"t": self.bhat["Coefficients"] / self.std_err_vars["SE"]})
        self.p_vals = pd.DataFrame({"p": pd.Series(2 * stats.t.cdf(-abs(self.t_vals["t"]), n - p),
                                                    index=self.bhat.index)})
        ci_width = stats.t.ppf(q=0.975, df=n-p)
        self.lower_conf = pd.DataFrame({"2.5% CI": self.bhat["Coefficients"] - ci_width*self.std_err_vars["SE"]})
        self.upper_conf = pd.DataFrame({"97.5% CI": self.bhat["Coefficients"] + ci_width*self.std_err_vars["SE"]})

        ret_val = pd.concat([self.bhat, self.std_err_vars, self.t_vals, self.p_vals, self.lower_conf, self.upper_conf], axis = 1)
        
        return ret_val 

    def likelihood(self, data=None):
        ''' Calculate likelihood for a fitted model on either original data or new data. '''

        if data is None:
            residuals = self.residuals.iloc[:, 0]
        else:
            y = self.re.evaluate(data)
            y_hat = self.predict(data, for_plot=False, confidence_interval=False, prediction_interval=False)
            residuals = y.iloc[:, 0] - y_hat.iloc[:, 0]

        var = self.std_err_est ** 2 
        n = len(residuals)

        return (2 * math.pi * var) ** (-n / 2) * math.exp(-1 / (2 * var) * (residuals ** 2).sum())

    def confidence_intervals(self, alpha = None, conf = None):
        ''' Calculate confidence intervals for fitted coefficients. Model must be fitted prior to execution.

        Arguments:
            alpha - A real value denoting the alpha of the confidence interval. CI Width = 1 - alpha / 2.
            conf - A real value denoting the confidecne interval width.
                Only one or the other of alpha or conf needs to be specified. 
                If neither are, a default value of conf = 0.95 will be used.
        
        Returns:    
            A DataFrame object containing the appropriate confidence intervals for all the coefficients.
        '''
        if alpha is None:
            if conf is None:
                conf = 0.95
            alpha = 1 - conf

        crit_prob = 1 - (alpha / 2)
        df = self.training_x.shape[0] - self.bhat.shape[0] # n - p
        crit_value = stats.t.ppf(crit_prob, df)
        
        se_vals = self.std_err_vars["SE"]
        width = crit_value * se_vals
        lower_bound = self.bhat["Coefficients"] - width
        upper_bound = self.bhat["Coefficients"] + width 
        return pd.DataFrame({str(round(1 - crit_prob, 5) * 100) + "%" : lower_bound, 
                             str(round(crit_prob, 5) * 100) + "%" : upper_bound})#, 
                             #index = self.bhat.index)

    def predict(self, data, for_plot = False, confidence_interval = False, prediction_interval = False):
        ''' Predict response values given some data for a fitted model.

        Arguments:
            data - A DataFrame object containing the explanatory values to base predictions off of.
            for_plot - A boolean flag to indicate if these predictions are computed for the purposes of plotting.
            confidence_interval - A real value indicating the width of confidence intervals for the prediction. 
                If not intervals are wanted, parameter is set to False.
            prediction_interval - A real value indicating the width of prediction intervals for the prediction. 
                If not intervals are wanted, parameter is set to False. 

        Returns:
            A DataFrame object containing the appropriate predictions and intervals.
        '''
        # Construct the X matrix
        X = self.ex.evaluate(data, fit = False)
        if self.intercept:
            X['Intercept'] = 1

        y_vals = X.dot(self.bhat).sum(axis = 1)
        predictions = pd.DataFrame({"Predicted " + str(self.re) : y_vals})
            
        if confidence_interval or prediction_interval:
            if confidence_interval:
                alpha = confidence_interval
                widths = self._confidence_interval_width(X, confidence_interval)
            else:
                alpha = prediction_interval
                widths = self._prediction_interval_width(X, prediction_interval)

            crit_prob = 1 - (alpha / 2)

            lower = y_vals - widths
            upper = y_vals + widths

            predictions[str(round(1 - crit_prob, 5) * 100) + "%"] = lower
            predictions[str(round(crit_prob, 5) * 100) + "%"] = upper

        
        return predictions
    
    def get_sse(self):
        ''' Get the SSE of a fitted model. '''
        sse = ((self.training_y.iloc[:,0] - self.fitted.iloc[:,0]) ** 2).sum()
        return sse
        
    def get_ssr(self):
        ''' Get the SSR of a fitted model. '''
        ssr = self.get_sst() - self.get_sse()
        return ssr
    
    def get_sst(self):
        ''' Get the SST of a fitted model. '''
        sst = ((self.training_y.iloc[:,0] - self.training_y.iloc[:,0].mean()) ** 2).sum()
        return sst
    
    def r_squared(self, X = None, y = None, adjusted = False, **kwargs):
        ''' Calculate the (adjusted) R^2 value of the model.
        This can be used as a metric within the sklearn ecosystem.

        Arguments:
            X - An optional DataFrame of the explanatory data to be used for calculating R^2. Default is the training data.
            Y - An optional DataFrame of the response data to be used for calculating R^2. Default is the training data.  
            adjusted - A boolean indicating if the R^2 value is adjusted (True) or not (False).

        Returns:
            A real value of the computed R^2 value.
        '''
        # Allow interfacing with sklearn's cross fold validation
        #self.fit(X, y)
        if X is None:
            X = self.training_data
        if y is None:
            y = self.training_y

        pred = self.predict(X)
        sse = ((y.iloc[:,0] - pred.iloc[:,0]) ** 2).sum()
        ssto = ((y.iloc[:,0] - y.iloc[:,0].mean()) ** 2).sum()

        if adjusted:
            numerator = sse
            denominator = ssto
        else:
            numerator = sse / (len(y) - len(self.training_x.columns) - 2)
            denominator = ssto / (len(y) - 1)
            
        return 1 - numerator / denominator 

    def score(self, X = None, y = None, adjusted = False, **kwargs):
        ''' Wrapper for sklearn api for cross fold validation. See LinearModel.r_squared. '''
        return self.r_squared(X, y, adjusted, **kwargs)

    def _prediction_interval_width(self, X_new, alpha = 0.05):
        ''' Helper function for calculating prediction interval widths. '''
        n = self.training_x.shape[0]
        p = X_new.shape[1]
        mse = self.get_sse() / (n - p)
        s_yhat_squared = (X_new.dot(self.var) * X_new).sum(axis = 1) # X_new_vect * var * X_new_vect^T (equivalent to np.diag(X_new.dot(self.var).dot(X_new.T)))
        s_pred_squared = mse + s_yhat_squared

        t_crit = stats.t.ppf(1 - (alpha / 2), n-p)

        return t_crit * (s_pred_squared ** 0.5)

    def _confidence_interval_width(self, X_new, alpha = 0.05):
        ''' Helper function for calculating confidence interval widths. '''
        n = self.training_x.shape[0]
        p = X_new.shape[1]
        s_yhat_squared = (X_new.dot(self.var) * X_new).sum(axis = 1) # X_new_vect * var * X_new_vect^T (equivalent to np.diag(X_new.dot(self.var).dot(X_new.T)))
        #t_crit = stats.t.ppf(1 - (alpha / 2), n-p)
        W_crit_squared = p * stats.f.ppf(1 - (alpha / 2), p, n-p)
        return (W_crit_squared ** 0.5) * (s_yhat_squared ** 0.5)
        
    def plot(
        self,
        categorize_residuals=True,
        jitter=None,
        confidence_band=False,
        prediction_band=False,
        original_y_space=True,
        transformed_y_space=False,
        alpha=0.5,
        **kwargs
    ):
        ''' Visualizes the fitted LinearModel and its line of best fit.

        Arguments:
            categorize_residuals - A boolean that indicates if the residual points should be colored by categories (True) or not (False).
            jitter - A boolean that indicates if residuals should be jittered in factor plots (True) or not (False).
            confidence_band - A real value that specifies the width of the confidence band to be plotted. If band not desired, parameter is set to False.
            prediction_band - A real value that specifies the width of the prediction band to be plotted. If band not desired, parameter is set to False.
            y_space - A str that indicates the type of output space for the y-axis. If set to 't', the transformed space will be plotted. 
                If set to 'o', the original or untransformed space will be plotted. If set to 'b', both will be plotted side-by-side.
            alpha - A real value that indicates the transparency of the residuals. Default is 0.5.
            kwargs - Additional named parameters that will be passed onto lower level matplotlib plotting functions.

        Returns:    
            A matplotlib plot appropriate visualization of the model.
        '''
        if confidence_band and prediction_band:
            raise Exception("One one of {confidence_band, prediction_band} may be set to True at a time.")

        terms = self.ex.reduce()
                        
        if original_y_space and transformed_y_space:
            fig, (ax_o, ax_t) = plt.subplots(1, 2, **kwargs)
            y_spaces = ['o', 't']
            axs = [ax_o, ax_t]
        elif transformed_y_space: # at least one of the two is False
            fig, ax_t = plt.subplots(1,1, **kwargs)
            y_spaces = ['t']
            axs = [ax_t]
        elif original_y_space:
            fig, ax_o = plt.subplots(1,1, **kwargs)
            y_spaces = ['o']
            axs = [ax_o]
        else:
            raise AssertionError("At least one of either 'original_y_space' or 'transformed_y_space' should be True in model.plot(...) call.")

        for y_space_type, ax in zip(y_spaces, axs):
            original_y_space = y_space_type == "o"

            # Redundant, we untransform in later function calls
            # TODO: Fix later
            y_vals = self.training_y[str(self.re)]
            if original_y_space:
                y_vals = self.re.untransform(y_vals)
            # Plotting Details:
            min_y = min(y_vals)
            max_y = max(y_vals)
            diff = (max_y - min_y) * 0.05
            min_y = min(min_y - diff, min_y + diff) # Add a small buffer
            max_y = max(max_y - diff, max_y + diff) # TODO: Check if min() and max() are necessary here

            plot_args = {
                "categorize_residuals": categorize_residuals,
                "jitter": jitter,
                "terms": terms,
                "confidence_band": confidence_band,
                "prediction_band": prediction_band,
                "original_y_space": original_y_space,
                "alpha": alpha,
                "plot_objs": {
                    "figure": fig,
                    "ax": ax,
                    "y": {
                        "min": min_y,
                        "max": max_y,
                        "name": str(self.re)
                    }
                }
            }

            if len(terms['Q']) == 1:
                self._plot_one_quant(**plot_args)
            elif len(terms['Q']) == 0 and len(terms['C']) > 0:
                self._plot_zero_quant(**plot_args) # TODO Make function
            else:
                raise Exception("Plotting line of best fit only expressions that reference a single variable.")
        return fig
        
    def _plot_zero_quant(self, categorize_residuals, jitter, terms, confidence_band, prediction_band, original_y_space, alpha, plot_objs):
        ''' A helper function for plotting models in the case no quantitiative variables are present. '''

        ax = plot_objs['ax']
        unique_cats = list(terms['C'])
        levels = [cat.levels for cat in unique_cats]
        level_amounts = [len(level_ls) for level_ls in levels]
        ml_index = level_amounts.index(max(level_amounts))
        ml_cat = unique_cats[ml_index]
        ml_levels = levels[ml_index]
        cats_wo_most = unique_cats[:]
        cats_wo_most.remove(ml_cat) # List of categorical variables without the ml_cat
        levels_wo_most = levels[:]
        levels_wo_most.remove(levels[ml_index]) # List of levels for categorical variables without the ml_cat
        single_cat = len(cats_wo_most) == 0
        if single_cat:
            level_combinations = [None]
        else:
            level_combinations = product(*levels_wo_most) # Cartesian product
        
        line_x = pd.DataFrame({str(ml_cat) : ml_levels}).reset_index() # To produce an index column to be used for the x-axis alignment
        points = pd.merge(self.training_data, line_x, on = str(ml_cat))

        plot_objs['x'] = {'name': 'index'}

        points["<Y_RESIDS_TO_PLOT>"] = self.re.evaluate(points)
        if original_y_space:
            points["<Y_RESIDS_TO_PLOT>"] = self.re.untransform(points["<Y_RESIDS_TO_PLOT>"]) # Inefficient due to transforming, then untransforming. Need to refactor later.

        plots = []
        labels = []
        linestyles = [':', '-.', '--', '-']
        for combination in level_combinations:
            points_indices = pd.Series([True] * len(points))
            if not single_cat:
                label = []
                for element, var in zip(combination, cats_wo_most):
                    name = str(var)
                    line_x[name] = element
                    label.append(str(element))
                    points_indices = points_indices & (points[name] == element) # Filter out points that don't apply to categories
                labels.append(", ".join(label))
            line_type = linestyles.pop()
            linestyles.insert(0, line_type)
            line_y = self.predict(line_x, for_plot = True)
            y_vals = line_y["Predicted " + plot_objs['y']['name']]
            if original_y_space:
                y_vals_to_plot = self.re.untransform(y_vals)
            else:
                y_vals_to_plot = y_vals
            plot, = ax.plot(line_x.index, y_vals_to_plot, linestyle = line_type)
            if jitter is None or jitter is True:
                variability = np.random.normal(scale = 0.025, size = sum(points_indices))
            else:
                variability = 0
            # Y values must come from points because earlier merge shuffles rows
            ax.scatter(points.loc[points_indices, 'index'] + variability, points.loc[points_indices, "<Y_RESIDS_TO_PLOT>"], c = "black" if single_cat else plot.get_color(), alpha = alpha)
            plots.append(plot)

            if confidence_band:
                self._plot_band(line_x, y_vals, plot.get_color(), original_y_space, plot_objs, True, confidence_band)
            elif prediction_band:
                self._plot_band(line_x, y_vals, plot.get_color(), original_y_space, plot_objs, False, prediction_band)


        if not single_cat and len(cats_wo_most) > 0:
            box = ax.get_position()
            ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])
            ax.legend(plots, labels, title = ", ".join([str(cat) for cat in cats_wo_most]), loc = "center left", bbox_to_anchor=(1, 0.5))
        ax.set_xlabel(str(ml_cat))
        ax.set_xticks(line_x.index)
        ax.set_xticklabels(line_x[str(ml_cat)])
        ax.set_ylabel(plot_objs['y']['name'] if not original_y_space else self.re.untransform_name())
        ax.grid()
        ax.set_ylim([plot_objs['y']['min'], plot_objs['y']['max']])

    def _plot_one_quant(self, categorize_residuals, jitter, terms, confidence_band, prediction_band, original_y_space, alpha, plot_objs):
        ''' A helper function for plotting models in the case only one quantitiative variable is present. Also support zero or more categorical variables.'''
        x_term = next(iter(terms['Q'])) # Get the "first" and only element in the set 
        x_name = str(x_term)
        x = self.training_data[x_name]
        min_x = min(x)
        max_x = max(x)
        diff = (max_x - min_x) * 0.05
        min_x = min(min_x - diff, min_x + diff) # Add a small buffer
        max_x = max(max_x - diff, max_x + diff) # TODO: Check if min() and max() are necessary here
        
        plot_objs['x'] = {"min" : min_x, "max" : max_x, "name" : x_name}
        
        # Quantitative inputs
        line_x = pd.DataFrame({x_name : np.linspace(min_x, max_x, 100)})
        
        if len(terms['C']) == 0:
            self._plot_one_quant_zero_cats(x, line_x, jitter, terms, confidence_band, prediction_band, original_y_space, alpha, plot_objs)
        else:
            self._plot_one_quant_some_cats(x, line_x, categorize_residuals, jitter, terms, confidence_band, prediction_band, original_y_space, alpha, plot_objs)

        ax = plot_objs['ax']
        ax.set_xlabel(x_name)
        ax.set_ylabel(plot_objs['y']['name'] if not original_y_space else self.re.untransform_name())
        ax.grid()
        ax.set_xlim([min_x, max_x])
        ax.set_ylim([plot_objs['y']['min'], plot_objs['y']['max']])
                                                      
    def _plot_one_quant_zero_cats(self, x, line_x, jitter, terms, confidence_band, prediction_band, original_y_space, alpha, plot_objs):
        ''' A helper function for plotting models in the case only one quantitiative variable and no categorical variables are present.'''

        x_name = plot_objs['x']['name']
        ax = plot_objs['ax']
        line_y = self.predict(line_x)
        y_vals = line_y["Predicted " + plot_objs['y']['name']]
        if original_y_space:
            y_vals_to_plot = self.re.untransform(y_vals)
        else:
            y_vals_to_plot = y_vals
        line_fit, = ax.plot(line_x[x_name], y_vals_to_plot)

        if confidence_band:
            self._plot_band(line_x, y_vals, line_fit.get_color(), original_y_space, plot_objs, True, confidence_band)
        elif prediction_band:
            self._plot_band(line_x, y_vals, line_fit.get_color(), original_y_space, plot_objs, False, prediction_band)

        training_y_vals = self.training_y[plot_objs['y']['name']]
        if original_y_space:
            training_y_vals = self.re.untransform(training_y_vals)

        ax.scatter(x, training_y_vals, c = "black", alpha = alpha)

    def _plot_band(self, line_x, y_vals, color, original_y_space, plot_objs, use_confidence = False, alpha = 0.05): # By default will plot prediction bands
        ''' A helper function to plot the confidence or prediction bands for a model. '''
        x_name = plot_objs['x']['name']
        X_new = self.ex.evaluate(line_x, fit = False)
        if self.intercept:
            X_new['Intercept'] = 1

        if use_confidence:
            widths = self._confidence_interval_width(X_new, alpha)
        else:
            widths = self._prediction_interval_width(X_new, alpha)

        lower = y_vals - widths
        upper = y_vals + widths

        if original_y_space:
            lower = self.re.untransform(lower)
            upper = self.re.untransform(upper)

        plot_objs['ax'].fill_between(x = line_x[x_name], y1 = lower, y2 = upper, color = color, alpha = 0.3)
        
        
    def _plot_one_quant_some_cats(self, x, line_x, categorize_residuals, jitter, terms, confidence_band, prediction_band, original_y_space, alpha, plot_objs):
        ''' A helper function for plotting models in the case only one quantitiative variable and one or more categorical variables are present.'''

        ax = plot_objs['ax']
        x_name = plot_objs['x']['name']
        y_name = plot_objs['y']['name']
        

        plots = []
        labels = []
        linestyles = [':', '-.', '--', '-']
        
        cats = list(terms['C'])
        cat_names = [str(cat) for cat in cats]
        levels = [cat.levels for cat in cats]
        level_combinations = product(*levels) #cartesian product of all combinations
        
        dummy_data = line_x.copy() # rest of columns set in next few lines
       
        training_y_vals = self.training_y[y_name]
        if original_y_space:
            training_y_vals = self.re.untransform(training_y_vals)

        for level_set in level_combinations:
            label = [] # To be used in legend
            for (cat,level) in zip(cats,level_set):
                dummy_data[str(cat)] = level # set dummy data for prediction
                label.append(str(level))
                               
            line_type = linestyles.pop() # rotate through line styles
            linestyles.insert(0, line_type)
            
            line_y = self.predict(dummy_data, for_plot = True)
            y_vals = line_y["Predicted " + y_name]
            if original_y_space:
                y_vals_to_plot = self.re.untransform(y_vals)
            else:
                y_vals_to_plot = y_vals
            plot, = ax.plot(dummy_data[x_name], y_vals_to_plot, linestyle = line_type)
            plots.append(plot)
            labels.append(", ".join(label))
            

            if categorize_residuals:
                indices_to_use = pd.Series([True] * len(x)) # gradually gets filtered out
                for (cat,level) in zip(cats,level_set):
                    indices_to_use = indices_to_use & (self.training_data[str(cat)] == level)
                ax.scatter(x[indices_to_use], training_y_vals[indices_to_use], c = plot.get_color(), alpha = alpha)
            
            if confidence_band:
                self._plot_band(dummy_data, y_vals, plot.get_color(), original_y_space, plot_objs, True, confidence_band)
            elif prediction_band:
                self._plot_band(dummy_data, y_vals, plot.get_color(), original_y_space, plot_objs, False, prediction_band)

        # Legend
        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])
        ax.legend(plots, labels, title = ", ".join(cat_names), loc = "center left", bbox_to_anchor = (1, 0.5))
        
        if not categorize_residuals:
            resids = ax.scatter(x, training_y_vals, c = "black", alpha = alpha)

    def residual_plots(self, **kwargs):
        ''' Plot the residual plots of the model.

        Arguments:
            kwargs - Named parameters that will be passed onto lower level matplotlib plotting functions.

        Returns:
            A tuple containing the matplotlib (figure, list of axes) for the residual plots.
        ''' 
        terms = list(self.training_x)
        fig, axs = plt.subplots(1, len(terms), **kwargs)
        for term, ax in zip(terms, axs):
            ax.scatter(self.training_x[str(term)], self.residuals['Residuals'])
            ax.set_xlabel(str(term))
            ax.set_ylabel("Residuals")
            ax.set_title(str(term) + " v. Residuals")
            ax.grid()
        return fig, axs
        
    def partial_plots(self, alpha = 0.5, **kwargs):
        ''' Plot the partial regression plots for the model

        Arguments:
            alpha - A real value indicating the transparency of the residuals. Default is 0.5.
            kwargs - Named parameters that will be passed onto lower level matplotlib plotting functions.

        Returns:
            A tuple containing the matplotlib (figure, list of axes) for the partial plots.
        '''
        #terms = self.ex.flatten(separate_interactions = False)
        terms = self.ex.get_terms()
        fig, axs = plt.subplots(1, len(terms), **kwargs)

        for i, ax in zip(range(0, len(terms)), axs):
        
            xi = terms[i]

            sans_xi = Combination(terms[:i] + terms[i+1:])
            yaxis = LinearModel(sans_xi, self.re)
            xaxis = LinearModel(sans_xi, xi)
            
            yaxis.fit(self.training_data)
            xaxis.fit(self.training_data)
            
            ax.scatter(xaxis.residuals["Residuals"], yaxis.residuals["Residuals"], alpha = alpha)
            ax.set_title("Leverage Plot for " + str(xi))

        return fig, axs

    # static method
    def ones_column(data):
        ''' Helper function to create a column of ones for the intercept. '''
        return pd.DataFrame({"Intercept" : np.repeat(1, data.shape[0])})

    def residual_diagnostic_plots(self, **kwargs):
        ''' Produce a matrix of four diagnostic plots: 
        the residual v. quantile plot, the residual v. fited values plot, the histogram of residuals, and the residual v. order plot.

        Arguments:
            kwargs - Named parameters that will be passed onto lower level matplotlib plotting functions.

        Returns:
            A tuple containing the matplotlib (figure, list of axes) for the partial plots.
        '''

        f, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, **kwargs)
        self.residual_quantile_plot(ax = ax1)
        self.residual_fitted_plot(ax = ax2)
        self.residual_histogram(ax = ax3)
        self.residual_order_plot(ax = ax4)

        f.suptitle("Residal Diagnostic Plots for " + str(self))

        return f, (ax1, ax2, ax3, ax4)

    def residual_quantile_plot(self, ax = None):
        ''' Produces the residual v. quantile plot of the model.

        Arguments:
            ax - An optional parameter that is a pregenerated Axis object.
        
        Returns:
            A rendered matplotlib axis object.
        '''
        if ax is None:
            f, ax = plt.subplots(1,1)

        stats.probplot(self.residuals["Residuals"], dist = "norm", plot = ax)
        ax.set_title("Residual Q-Q Plot")
        return ax

    def residual_fitted_plot(self, ax = None):
        ''' Produces the residual v. fitted values plot of the model.

        Arguments:
            ax - An optional parameter that is a pregenerated Axis object.
        
        Returns:
            A rendered matplotlib axis object.
        '''
        if ax is None:
            f, ax = plt.subplots(1,1)

        ax.scatter(self.fitted["Fitted"], self.residuals["Residuals"])
        ax.set_title("Fitted Values v. Residuals")
        ax.set_xlabel("Fitted Value")
        ax.set_ylabel("Residual")

        return ax

    def residual_histogram(self, ax = None):
        ''' Produces the residual histogram of the model.

        Arguments:
            ax - An optional parameter that is a pregenerated Axis object.
        
        Returns:
            A rendered matplotlib axis object.
        '''
        if ax is None:
            f, ax = plt.subplots(1,1)
        
        ax.hist(self.residuals["Residuals"])
        ax.set_title("Histogram of Residuals")
        ax.set_xlabel("Residual")
        ax.set_ylabel("Frequency")

        return ax

    def residual_order_plot(self, ax = None):
        ''' Produces the residual v. order plot of the model.

        Arguments:
            ax - An optional parameter that is a pregenerated Axis object.
        
        Returns:
            A rendered matplotlib axis object.
        '''
        if ax is None:
            f, ax = plt.subplots(1,1)

        ax.plot(self.residuals.index, self.residuals["Residuals"], "o-")
        ax.set_title("Order v. Residuals")
        ax.set_xlabel("Row Index")
        ax.set_ylabel("Residual")

        return ax

