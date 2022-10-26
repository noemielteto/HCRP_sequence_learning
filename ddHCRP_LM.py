import os, sys
import copy
import numpy as np
from random import random as randomvalue_0_1
e=np.e
import math
import scipy
from scipy.stats import pearsonr
import time
import pandas as pd
pd.options.mode.chained_assignment = None  # silence SettingWithCopyWarning; default='warn'
import sklearn
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt
import seaborn as sns
import itertools
#sns.set(style="white",context='paper',rc={"lines.linewidth": 1.5})
#np.set_printoptions(suppress=True)
sns.set(style="white",context='paper',font_scale=2)

from utils import *

class HCRP_LM():

    """
    Hierarchical Chinese restaurant process (HCRP) language model based on
    Yee Whye Teh (2006). The model learns a hierarchy of n-grams and makes a
    sequence prediction by smoothing across all n-gram levels and combining
    the predictive information from them. This version has been expended to be
    optionally distance-dependent meaning that more recent n-grams are more
    expected.

    Attributes
    ----------
    strength : array-like
        vector of strength (alpha) parameters for each hierarchy level
    n : int
        the length of the strength vector; defines the number of levels
        (i.e. the maximum chunk size) that we want to consider; corresponds to
        (n-1)th order Markov model; for instance, n=2 corresponds to a 2-gram
        model or first-order Markov model
    decay_constant : array-like
        if defined, the model will be distance-dependent, otherwise not;
        vector of decay constant (lambda) parameters for each hierarchy level;
        its length should be equal to the length of the strength vector;
    dishes : array-like
        vector of types of observations (e.g. words, a feature of the stimulus,
        etc.); by default we will learn this from the data
    number_of_dishes : int
        length of the dishes vector; the number of types of observations (e.g.
        vocabulary size)
    n_samples : int, optional
        independent samples of the HCRP seating arrangements; predictions will
        be based on averaging across these samples
    samples : dictionary
        dictionary of dictionaries; its structure depends on whether the model
        is distance-dependent; if not distance-dependent, the structure is:
        samples[sample][restaurant] = table_counts of length n_dishes
        and will contain the total number of observations per observation type
        (i.e. dish)

        if distance-dependent, the structure is:
        samples[sample][restaurant] = matrix of size n_dishes * 1000
        and will contain the time stamps of the last 1000 instances per
        observation type (i.e. dish)
    """

    def __init__(self, strength, decay_constant=False, n_samples=5, dishes=None):

        """
        Parameters
        ----------
        strength : array-like
            vector of strength (alpha) parameters for each hierarchy level;
            the length of this vector will also define the number of levels
            (i.e. the maximum chunk size that we want to consider)
        decay_constant : array-like, optional
            if defined, the model will be distance-dependent, otherwise not;
            vector of decay constant (lambda) parameters for each hierarchy level;
            its length should be equal to the length of the strength vector;
        n_samples : int, optional
            independent samples of the HCRP seating arrangements; predictions will
            be based on averaging across these samples
        dishes : array-like, optional
            vector of types of observations (e.g. words, a feature of the stimulus,
            etc.); by default we will learn this from the data
        """

        self.description = "Hierarchical chinese restaurant process language model based on Yee Whye Teh (2006)"
        self.strength = strength
        self.decay_constant = decay_constant
        self.n = len(strength)

        self.dishes = dishes if dishes is not None else []
        self.number_of_dishes = len(self.dishes)

        self.n_samples = n_samples
        self.samples = dict()
        for sample in range(n_samples):
            self.samples[sample] = dict()

    def __repr__(self):
        return ('HCRP(n={self.n}, strength={self.strength}, decay_constant={self.decay_constant})').format(self=self)

    def word_probability(self, t, u, w, sample, n=None, compute_seat_odds=False, seat_odds=None):

        """
        Computes the likelihood of the next element w (e.g. word) after
        sequential context u (e.g. n-1 previous words). Constitutes the
        generative process of the HCRP: computing the likelihood of an
        observation via the back-off procedure.

        Parameters
        ----------
        t : int
            rank of the element in the sequence
        u : array-like
            vector of previous sequence elements; sequence context; in the HCRP
            analogy, corresponds to restaurant
        w : str
            identity of element whose likelihood we are computing; in the HCRP
            analogy, corresponds to dish
        sample : int
            HCRP sample index
        n : int, optional
            can serve to truncate predictive context u; even if we want to
            consider the maximum context length, n is needed as an auxiliary
            variable to track the n-gram levels (context length doesn't serve
            the same purpose, because we want to continue the recursion even at
            context length 0 and finish after that).
        compute_seat_odds : bool, optional
            whether we want to compute the odds ratio of seating or back-off
            from each level (reflects the relative contribution of n-gram levels
            to the overall prediction; for interpretation or visualisation
            purposes)
        seat_odds : array-like, optional
            vector of odds ratio of seating or back-off from each level
            (reflects the relative contribution of n-gram levels to the overall
            prediction; for interpretation or visualisation purposes)
        """

        if w not in self.dishes:
            self.dishes.append(w)
            self.number_of_dishes += 1

        w_i = self.dishes.index(w)

        if n is None:

            u = u[-self.n+1:]  # truncate u to maximum context depth
            n = len(u)+1

            if compute_seat_odds:
                seat_odds = np.zeros(self.n)

        if n == 0:
            return (1 / self.number_of_dishes, seat_odds)  # G_0 prior: global mean vector with a uniform value of 1/vocabulary_size

        str_u = str(u)

        # no restaurant yet:
        if str_u not in self.samples[sample].keys():

            d_u, d_u_w = 0,0

            if self.decay_constant:
                self.samples[sample][str_u] = np.full((self.number_of_dishes, 1000), np.nan)

            else:
                self.samples[sample][str_u] = np.zeros(self.number_of_dishes)

        # no table yet
        elif self.samples[sample][str_u].shape[0] <= w_i:

            d_u_w = 0

            if self.decay_constant:

                while len(self.samples[sample][str_u])<len(self.dishes):
                    self.samples[sample][str_u] = np.vstack((self.samples[sample][str_u], np.full(1000, np.nan)))
                # self.samples[sample][str_u] = np.vstack((self.samples[sample][str_u], np.full(1000, np.nan)))

                timestamps_u = self.samples[sample][str_u][~np.isnan(self.samples[sample][str_u])].ravel()
                distances_u = t - timestamps_u
                decay_constant = self.decay_constant[len(u)]
                d_u = np.sum(e**(-distances_u/decay_constant))

            else:

                while len(self.samples[sample][str_u])<len(self.dishes):
                    self.samples[sample][str_u] = np.append(self.samples[sample][str_u], 0)
                # self.samples[sample][str_u] = np.append(self.samples[sample][str_u], 0)

                d_u = self.samples[sample][str_u].sum()

        else:

            if self.decay_constant:

                timestamps_u = self.samples[sample][str_u][~np.isnan(self.samples[sample][str_u])].ravel()
                timestamps_u_w = self.samples[sample][str_u][w_i][~np.isnan(self.samples[sample][str_u][w_i])]

                distances_u = t - timestamps_u
                decay_constant = self.decay_constant[len(u)]
                d_u = np.sum(e**(-distances_u/decay_constant))

                distances_u_w = t - timestamps_u_w
                d_u_w = np.sum(e**(-distances_u_w/decay_constant))

            else:
                d_u     = self.samples[sample][str_u].sum()
                d_u_w   = self.samples[sample][str_u][w_i]

        strength_u = self.strength[len(u)]

        prob_seat       = (d_u_w / (d_u+strength_u))
        prob_backoff    = (strength_u / (d_u+strength_u)) * self.word_probability(t, u[1:], w, sample, n-1, compute_seat_odds, seat_odds)[0]
        prob = prob_seat + prob_backoff

        if compute_seat_odds:
            seat_odds[n-1] = prob_seat/prob_backoff

        return (prob, seat_odds)

    def word_probability_all_samples(self, t, u, w):
        """
        Marginalizes the likelihood of current element w in the sequential
        context of u across the independent HCRP samples.

        Parameters
        ----------
        t : int
            rank of the element in the sequence
        u : array-like
            vector of previous sequence elements; sequence context; in the HCRP
            analogy, corresponds to restaurant
        w : str
            identity of element whose likelihood we are computing; in the HCRP
            analogy, corresponds to dish
        """
        sum_word_probabilities = 0
        for sample in self.samples.keys():
            sum_word_probabilities += self.word_probability(t, u, w, sample)[0]
        return sum_word_probabilities/len(self.samples.keys())

    def get_predictive_distribution(self, t, u):
        """
        Compute predictive probability distribution over the current element w
        given the sequential context of u.

        Parameters
        ----------
        t : int
            rank of the element in the sequence
        u : array-like
            vector of previous sequence elements; sequence context; in the HCRP
            analogy, corresponds to restaurant
        """
        distr = np.zeros(len(self.dishes))
        for i, w in enumerate(self.dishes):
            distr[i] = self.word_probability_all_samples(t, u, w)
        return distr

    def predict_next_word(self, t, u):
        """
        Compute predictive probability distribution over the current element w
        given the sequential context of u.

        Parameters
        ----------
        t : int
            rank of the element in the sequence
        u : array-like
            vector of previous sequence elements; sequence context; in the HCRP
            analogy, corresponds to restaurant
        """
        distr = self.get_predictive_distribution(t, u)
        return np.random.choice(a=self.dishes, p=distr)

    #@profile
    def add_customer(self, t, u, w, sample, n=None):

        """
        Update the model with new element w (e.g. word) observed in sequential
        context u (e.g. n-1 previous words). Constitutes the recognition process
        of the HCRP: update the HCRP seating arrangements with new observation.

        Parameters
        ----------
        t : int
            rank of the element in the sequence
        u : array-like
            vector of previous sequence elements; sequence context; in the HCRP
            analogy, corresponds to restaurant
        w : str
            identity of element whose likelihood we are computing; in the HCRP
            analogy, corresponds to dish
        sample : int
            HCRP sample index
        n : int, optional
            can serve to truncate predictive context u; even if we want to
            consider the maximum context length, n is needed as an auxiliary
            variable to track the n-gram levels (context length doesn't serve
            the same purpose, because we want to continue the recursion even at
            context length 0 and finish after that).
        """

        if w not in self.dishes:
            self.dishes.append(w)
            self.number_of_dishes += 1

        w_i = self.dishes.index(w)

        if n is None:
            u = u[-self.n+1:]  # truncate u to maximum context depth
            n = len(u)+1

        if n==0:
            return

        else:

            str_u = str(u)

            # no restaurant yet:
            if str_u not in self.samples[sample].keys():
                d_u_w = 0
                if self.decay_constant:
                    self.samples[sample][str_u] = np.full((self.number_of_dishes, 1000), np.nan)
                    self.samples[sample][str_u][w_i][0] = t
                else:
                    self.samples[sample][str_u] = np.zeros(self.number_of_dishes)
                    self.samples[sample][str_u][w_i] = 1

            # no table yet
            elif self.samples[sample][str_u].shape[0] <= w_i:

                d_u_w = 0

                if self.decay_constant:

                    while len(self.samples[sample][str_u])<len(self.dishes):
                        self.samples[sample][str_u] = np.vstack((self.samples[sample][str_u], np.full(1000, np.nan)))
                    # self.samples[sample][str_u] = np.vstack((self.samples[sample][str_u], np.full(1000, np.nan))
                    self.samples[sample][str_u][w_i][0] = t

                    timestamps_u = self.samples[sample][str_u][~np.isnan(self.samples[sample][str_u])].ravel()
                    distances_u = t - timestamps_u
                    decay_constant = self.decay_constant[len(u)]
                    d_u = np.sum(e**(-distances_u/decay_constant))

                else:

                    while len(self.samples[sample][str_u])<len(self.dishes):
                        self.samples[sample][str_u] = np.append(self.samples[sample][str_u], 0)
                    # self.samples[sample][str_u] = np.append(self.samples[sample][str_u], 0)
                    self.samples[sample][str_u][w_i] = 1

                    d_u = self.samples[sample][str_u].sum()

            else:

                if self.decay_constant:

                    timestamps_u_w = self.samples[sample][str_u][w_i][~np.isnan(self.samples[sample][str_u][w_i])]
                    decay_constant = self.decay_constant[len(u)]

                    # no table with this dish yet:
                    if not len(timestamps_u_w):
                        d_u_w = 0

                    else:
                        distances_u_w = t - timestamps_u_w
                        d_u_w = np.sum(e**(-distances_u_w/decay_constant))

                    if len(timestamps_u_w)<1000:
                        self.samples[sample][str_u][w_i][len(timestamps_u_w)] = t
                    else:
                        self.samples[sample][str_u][w_i] = np.append(self.samples[sample][str_u][w_i][1:], t) # if 1000 values stored, drop one oldest

                else:
                    d_u_w = self.samples[sample][str_u][w_i]
                    self.samples[sample][str_u][w_i] += 1


            # choose to backoff
            unnormalized_probs = [d_u_w] + [self.strength[len(u)] * self.word_probability(t, u[1:], w, sample, n-1)[0]]
            normalized_prob_of_seating_at_old = d_u_w/sum(unnormalized_probs)

            # seated at existing table -> return
            if normalized_prob_of_seating_at_old > np.random.rand(): return

            # opened new table -> backoff
            else:
                self.add_customer(t, u[1:], w, sample, n-1)  # backoff
                return


    def fit_onesample(self, sample, corpus_segments, choices_segments=False, observation='corpus', t_start=0, online_predict=False, compute_seat_odds=False, compute_context_importance=False, frozen=True):

        if frozen:

            t_end = 0
            for i_segment in range(len(corpus_segments)):
                # print(i_segment)
                corpus, choices = corpus_segments[i_segment], choices_segments[i_segment]

                for t in range(len(corpus)):

                    t_g = t+t_end  # t_global

                    u, w, choice = corpus[max(0, t - self.n + 1):t], corpus[t], choices[t]
                    self.add_customer(t_g+t_start, u, w, sample)

                t_end = t_g+1

            t_end = 0
            for i_segment in range(len(corpus_segments)):
                corpus, choices = corpus_segments[i_segment], choices_segments[i_segment]

                for t in range(len(corpus)):

                    t_g = t+t_end  # t_global

                    u, w, choice = corpus[max(0, t - self.n + 1):t], corpus[t], choices[t]
                    choice_prob, seat_odds = self.word_probability(t=t_g+t_start, u=u, w=choice, sample=sample, n=None, compute_seat_odds=compute_seat_odds)

                    self.sample_choice_probs[sample][t_g] = choice_prob

                    if compute_seat_odds:
                        self.sample_seat_odds[sample][t_g] = seat_odds

                    if online_predict:
                        for other_w in self.dishes:
                            self.sample_predictive_distr[sample][t_g][self.dishes.index(other_w)], seat_odds = self.word_probability(t_g+t_start, u, other_w, sample)

                        if compute_context_importance:
                            for context_len in range(self.n):
                                word_probs_given_context_len = np.zeros(self.number_of_dishes)

                                context = u[-context_len:] if context_len>0 else []
                                for other_w in self.dishes:
                                    word_probs_given_context_len[self.dishes.index(other_w)], seat_odds = self.word_probability(t=t_g+t_start, u=context, w=other_w, sample=sample, n=None)

                                KL_div = scipy.stats.entropy(word_probs_given_context_len, self.sample_predictive_distr[sample][t_g])
                                self.sample_context_importance[sample][t_g][context_len] = KL_div

                t_end = t_g+1

        else:

            t_end = 0

            for i_segment in range(len(corpus_segments)):
                corpus, choices = corpus_segments[i_segment], choices_segments[i_segment]

                for t in range(len(corpus)):

                    t_g = t+t_end  # t_global

                    u, w, choice = corpus[max(0, t - self.n + 1):t], corpus[t], choices[t]
                    choice_prob, seat_odds = self.word_probability(t=t_g+t_start, u=u, w=choice, sample=sample, n=None, seat_odds=compute_seat_odds)

                    self.sample_choice_probs[sample][t_g] = choice_prob

                    if compute_seat_odds:
                        self.sample_seat_odds[sample][t_g] = seat_odds

                    if online_predict:
                        for other_w in self.dishes:
                            prob, seat_odds = self.word_probability(t=t_g+t_start, u=u, w=other_w, sample=sample, n=None)
                            self.sample_predictive_distr[sample][t_g][self.dishes.index(other_w)] = prob

                        if compute_context_importance:
                            for context_len in range(self.n):
                                word_probs_given_context_len = np.zeros(self.number_of_dishes)

                                context = u[-context_len:] if context_len>0 else []
                                for other_w in self.dishes:

                                    word_probs_given_context_len[self.dishes.index(other_w)], seat_odds = self.word_probability(t=t_g+t_start, u=context, w=other_w, sample=sample, n=None)

                                KL_div = scipy.stats.entropy(word_probs_given_context_len, self.sample_predictive_distr[sample][t_g])
                                self.sample_context_importance[sample][t_g][context_len] = KL_div

                    if observation == 'corpus':
                        self.add_customer(t_g+t_start, u, w, sample)
                    elif observation == 'choices':
                        self.add_customer(t_g+t_start, u, choice, sample)

                    self.n_customers[sample][t_g] = np.mean([np.isfinite(self.samples[sample][rest]).sum().sum() for rest in self.samples[sample].keys()])

                t_end = t_g+1

    def fit(self, corpus_segments, choices_segments=False, observation='corpus', t_start=0, online_predict=False, compute_seat_odds=False, compute_context_importance=False, frozen=True):

        if not any(isinstance(i, list) for i in corpus_segments):
            corpus_segments = [corpus_segments]

        self.n_customers = np.zeros((self.n_samples, len(flatten(corpus_segments))))

        if choices_segments==False:
            choices_segments = corpus_segments
        else:
            if not any(isinstance(i, list) for i in choices_segments):
                choices_segments = [choices_segments]

        self.sample_choice_probs = np.zeros((self.n_samples, len(flatten(corpus_segments))))
        if online_predict:

            self.dishes = sorted(list(set([element for segment in corpus_segments for element in segment])))
            self.number_of_dishes = len(self.dishes)
            self.sample_predictive_distr = np.zeros((self.n_samples, len(flatten(corpus_segments)), self.number_of_dishes))

            if compute_context_importance:
                self.sample_context_importance = np.zeros((self.n_samples, len(flatten(corpus_segments)), self.n))
        if compute_seat_odds:
            self.sample_seat_odds = np.zeros((self.n_samples, len(flatten(corpus_segments)), self.n))

        for sample in self.samples.keys():
            self.fit_onesample( sample                      = sample,
                                corpus_segments             = corpus_segments,
                                choices_segments            = choices_segments,
                                observation                 = observation,
                                t_start                     = t_start,
                                online_predict              = online_predict,
                                compute_seat_odds           = compute_seat_odds,
                                compute_context_importance  = compute_context_importance,
                                frozen                      = frozen)

        self.choice_probs = np.mean(self.sample_choice_probs, axis=0)

        if online_predict:

            self.predictive_distr = np.mean(self.sample_predictive_distr, axis=0)
            index_of_most_likely_events = np.argmax(self.predictive_distr, axis=1)
            self.event_predictions = np.zeros(len(flatten(corpus_segments)), dtype='str')
            for i, dish in enumerate(self.dishes): self.event_predictions[index_of_most_likely_events==i] = dish

            if compute_context_importance:
                self.context_importance = np.mean(self.sample_context_importance, axis=0)

        if compute_seat_odds:
            self.seat_odds = np.mean(self.sample_seat_odds, axis=0)

    def negLL(self):
        return -np.sum(np.log(np.array(self.choice_probs)))


################################################################################

def fit_response_model(model_predictive_probabilities, lowlevel_predictors, subdf, mask=None, return_predicted_RT_components=False):

    if mask is None: mask = np.array([True]*len(subdf))

    X            = np.hstack((subdf[lowlevel_predictors].values,
                                -np.log(model_predictive_probabilities).reshape(-1,1)))
    y            = subdf.measured_RT.values

    response_model = LinearRegression(fit_intercept=True).fit(X[mask], y[mask])
    predicted_RTs = response_model.predict(X).ravel()

    if return_predicted_RT_components:

        predicted_RT_components = response_model.coef_ * X
        intercept = np.full(X.shape[0], response_model.intercept_).reshape(-1, 1)
        predicted_RT_components = np.append(intercept, predicted_RT_components, axis=1)

        return response_model, predicted_RTs, predicted_RT_components

    else:
        return response_model, predicted_RTs

def compute_NLL_of_HCRP(m, t_start, subdf, lowlevel_predictors, mask, offline_dist, resp_noise, frozen=True):

    corpus_segments  = list(subdf.event.astype('str'))
    choices_segments = list(subdf.choice.astype('str'))
    session          = subdf.Session.iloc[0]

    m.fit(t_start            = t_start,
            corpus_segments  = corpus_segments,
            choices_segments = choices_segments,
            frozen           = frozen)

    HCRP_response_model, HCRP_predicted_RT    = fit_response_model(model_predictive_probabilities = m.choice_probs,
                                                                    lowlevel_predictors           = lowlevel_predictors,
                                                                    subdf                         = subdf,
                                                                    mask                          = mask)

    # We evaluate the log likelihoods of the log RTs because we want less of a heavy tail, assuming Gaussian noise in our likelihood function
    NLL = compute_NLL(np.log(subdf.measured_RT.values), np.log(HCRP_predicted_RT), resp_noise, mask)

    return HCRP_response_model, HCRP_predicted_RT, NLL
