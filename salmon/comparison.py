from .model import *
from scipy.stats import f

import numpy as np
import pandas as pd

def anova(model1, model2 = None):
    if model2 is None:
        return _anova_terms(model1)
    elif is_subset(model1, model2):
        return _anova_models(model1, model2)
    elif is_subset(model2, model1):
        return _anova_models(model2, model1)
    else:
        raise Exception("Parameters must either be one model or two models where one is a subset of the other.")
        
# checks if model1 contains all the terms of model2
def is_subset(model1, model2):
    if not model1.given_re.__sim__(model2.given_re):
        # Models should both have the same response variable
        return False
    
    terms1 = set(model1.ex.get_terms())
    terms2 = set(model2.ex.get_terms())
    return terms2.issubset(terms1)

def _calc_stats(numer_ss, numer_df, denom_ms, denom_df):
    numer_ms = numer_ss / numer_df
    f_val = numer_ms / denom_ms
    p_val = 1 - f.cdf(f_val, numer_df, denom_df)
    return (numer_ms, f_val, p_val)

def _process_term(orig_model, term):
    new_model = LinearModel(orig_model.given_ex - term, orig_model.given_re)
    new_model.fit(orig_model.training_data)
    return new_model.get_ssr()
    
def _anova_terms(model):
    reg_df = model.ex.get_dof()
    total_df = len(model.training_x) - 1
    error_df = total_df - reg_df
  
    # Full model values
    r_sse = model.get_sse()
    r_ssr = model.get_ssr()
    r_sst = model.get_sst()
    
    r_mse = sse / error_df
    r_msr, r_f_val, r_p_val = _calc_stats(r_ssr, reg_df, r_mse, error_df)
    
    # Calculate the general terms now
    indices = ["Regression"]
    adj_ss = [r_ssr]
    adj_ms = [r_msr]
    f_vals = [r_f_val]
    p_vals = [r_p_val]
    dfs = [reg_df]
    
    terms = model.ex.get_terms()
    for term in terms:
        term_df = term.get_dof()
        term_ss = r_ssr - _process_term(model, term)
        term_ms, term_f, term_p = _calc_stats(term_ss, term_df, r_mse, error_df)
        indices.append(">> " + str(term))
        adj_ss.append(term_ss)
        adj_ms.append(term_ms)
        dfs.append(term_df)
        f_vals.append(term_f)
        p_vals.append(term_p)
    
    
    # Finish off the dataframe's values
    indices += ["Error", "Total"]
    adj_ss += [r_sse, r_sst]
    adj_ms += [r_mse]
    dfs += [error_df, total_df]
    f_vals += [np.nan, np.nan]
    p_vals += [np.nan, np.nan]
    
    return pd.DataFrame({
            "DF" : dfs,
            "Adj SS": adj_ss,
            "Adj MS" : adj_ms,
            "F-Value" : f_vals,
            "P-Value" : p_vals
        }, index = indices)

def _anova_models(full_model, reduced_model):
    full_label = str(full_model)
    reduced_label = str(reduced_model)
    
    