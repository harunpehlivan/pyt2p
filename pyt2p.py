import csv
import pickle
from nltk.corpus import cmudict
from numpy import log,exp

ALLOWABLES_FNAME = 'allowables.csv'
CROSSVAL_NFOLDS = 10
DEPTH_TEST_STEP = 5

CMU = cmudict.dict()

class ViterbiCell(object):
    def __init__(self, name):
        self.name = name

        self.paths = []

    def get_all_paths(self):
        return self.paths

    def get_best_path(self):
        if not len(self.paths):
            return []

        self.paths.sort(cmp=lambda x,y: cmp(x[-1][-1],y[-1][-1]))
        return self.paths[-1]

class ViterbiAligner(object):
    def __init__(self, word, pronun, alignment_probabilities):
        self.word = word
        self.pronun = pronun
        self.alignment_probabilities = alignment_probabilities

        # probably unnecessary to use two representations for this
        self.cells = {}
        self.grid = []

        self.initialize_grid()

    def initialize_grid(self):
        word_pops = [self.word[n:] for n in range(len(self.word)+1)]
        pronun_pops = [self.pronun[n:] for n in range(len(self.pronun)+1)]

        for w in word_pops:
            word_row = []
            for p in pronun_pops:
                p = ' '.join(p)
                # add to the row so we can reference it by grid number
                cell_name = (w,p)
                word_row.append(cell_name)

                # add to the celldict so we can reference it by cell name
                this_cell = ViterbiCell(cell_name)
                self.cells[cell_name] = this_cell

            self.grid.append(word_row)

    def align(self):
        bottom_right_cellname = self.grid[0][0]
        bottom_right_cell = self.cells[bottom_right_cellname]
        bottom_right_cell.paths.append([])

        for row_idx in range(len(self.grid)):
            row = self.grid[row_idx]
            for cell_idx in range(len(row)):
                cell_name = row[cell_idx]
                cell = self.cells[cell_name]

                # try to go diagonal first
                try:
                    diag_cellname = self.grid[row_idx+1][cell_idx+1]
                    diag_cell = self.cells[diag_cellname]
                except IndexError: diag_cell = None

                # try to go epsilon (deletion)
                try:
                    epsilon_cellname = self.grid[row_idx+1][cell_idx]
                    epsilon_cell = self.cells[epsilon_cellname]
                except IndexError: epsilon_cell = None

                # if we're at the end, or the top row, there's no reason to try
                if (diag_cell is None) and (epsilon_cell is None):
                    continue

                # we're guaranteed to have a next letter at this point
                remaining_letters = cell_name[0]
                next_letter = remaining_letters[0]

                # clear if we've got a weird character
                if next_letter not in self.alignment_probabilities:
                    next_letter = ''

                # try to go epsilon first
                for path in cell.paths:
                    try: path_prob = path[-1][-1]
                    except IndexError: path_prob = 0
                    if epsilon_cell is not None:
                        # there's probably always an epsilon probability
                        epsilon_prob = self.alignment_probabilities[next_letter]['']

                        path_out = path + [(row_idx,cell_idx,
                                            next_letter,
                                            '',
                                            path_prob+epsilon_prob)]

                        epsilon_cell.paths.append(path_out)

                # now, if we can go diagonal (we're not along the right edge)
                if diag_cell is None:
                    continue

                remaining_phones = cell_name[1].split()
                next_phone = remaining_phones[0]

                if next_phone in self.alignment_probabilities[next_letter]:
                    diag_prob = self.alignment_probabilities[next_letter][next_phone]

                    for path in cell.paths:
                        try: path_prob = path[-1][-1]
                        except IndexError: path_prob = 0
                        path_out = path + [(row_idx,cell_idx,
                                            next_letter,
                                            next_phone,
                                            path_prob+diag_prob)]
                        diag_cell.paths.append(path_out)

                # finally, try to jump two phones
                next_two_phones = remaining_phones[:2]
                if len(next_two_phones) == 2:
                    biphone = '-'.join(next_two_phones)
                    if biphone in self.alignment_probabilities[next_letter]:
                        biphone_prob = self.alignment_probabilities[next_letter][biphone]

                        # figure out the new cell name
                        new_cell_letters = remaining_letters[1:]
                        new_cell_phones = ' '.join(remaining_phones[2:])

                        new_cell = self.cells[(new_cell_letters,new_cell_phones)]

                        for path in cell.paths:
                            try: path_prob = path[-1][-1]
                            except IndexError: path_prob = 0
                            path_out = path+[(row_idx,cell_idx,
                                            next_letter,
                                            biphone,
                                            path_prob+biphone_prob)]
                            new_cell.paths.append(path_out)

    def get_all_paths(self):
        last_cell = self.cells[('','')]
        return last_cell.get_all_paths()

    def get_best_path(self):
        last_cell = self.cells[('','')]
        return last_cell.get_best_path()


class ViterbiEM(object):
    def __init__(self, pronun_dict, allowables):
        self.pronun_dict = pronun_dict
        self.alignment_probabilities = [allowables]
        self.iteration_number = 0
        self.log_likelihoods = []

        self.best_alignment = None

    def run_EM(self, n_iterations = 5):
        for iteration in range(n_iterations):
            self.iteration_number += 1
            print "iteration",iteration
            prev_alignment_probabilities = self.alignment_probabilities[-1]
            all_alignments = self.e_step(prev_alignment_probabilities)

            new_alignment_probabilities = self.m_step(all_alignments)
            if prev_alignment_probabilities == new_alignment_probabilities:
                break
            self.alignment_probabilities.append(new_alignment_probabilities)

    def e_step(self, probs):
        alignments = []
        for word in sorted(self.pronun_dict.keys()):
            pronun = [l.lower() for l in self.pronun_dict[word][0]]
            print self.iteration_number,word,pronun

            v = ViterbiAligner(word, pronun, probs)
            v.align()
            alignments += v.get_all_paths()
            del v
        return alignments

    def m_step(self, alignments):
        # keep track of likelihood
        this_log_likelihood = 0

        pseudocounts = {}
        for align in alignments:
            if not len(align):
                continue
            path_prob = exp(align[-1][-1])
            path_log_prob = align[-1][-1]
            for pair in align:
                letter = pair[-3]
                phone = pair[-2]
                if letter not in pseudocounts:
                    pseudocounts[letter] = {}
                if phone not in pseudocounts[letter]:
                    pseudocounts[letter][phone] = 0

                #pseudocounts[letter][phone] += path_prob
                pseudocounts[letter][phone] += 1
                this_log_likelihood += path_log_prob

        self.log_likelihoods.append(this_log_likelihood)

        pseudoprobs = {}
        for letter in pseudocounts:
            pseudoprobs[letter] = {}
            letter_total = log(sum(pseudocounts[letter].values()))
            for phone in pseudocounts[letter]:
                phone_total = log(pseudocounts[letter][phone])
                phone_prob = phone_total - letter_total
                pseudoprobs[letter][phone] = phone_prob

        return pseudoprobs


def read_allowables(fname):
    allowables = {}

    with open(fname,'U') as f:
        freader = csv.reader(f)
        for row in freader:
            letter = row[0]
            allowables[letter] = {}

            phones = row[1:]
            for phone in phones:
                allowables[letter][phone] = 0

    return allowables

def build_features(alignment, letter_dict, phone_dict):
    features = []
    targets = []
    for i in range(len(alignment)):
        this_features = []

        for window_i in range(i-3,i+4):
            if window_i < 0 or window_i >= len(alignment):
                letter = '#'
            else:
                letter = alignment[window_i][-3]
            this_features.append(letter_dict[letter])

        features.append(this_features)

        phone = alignment[i][-2]
        targets.append(phone_dict[phone])

    return features, targets

def build_int_translators(alignment_probabilities):
    letters = alignment_probabilities.keys()
    letters.append('#')
    letters.sort()
    letter_dict = dict(zip(letters, range(len(letters))))

    phones = set()
    for letter in alignment_probabilities:
        for phone in alignment_probabilities[letter]:
            phones.add(phone)
    phones = list(phones)
    phones.sort()
    phone_dict = dict(zip(phones, range(len(phones))))

    return letter_dict,phone_dict


if __name__ == "__main__":
    '''
    allowables = read_allowables(ALLOWABLES_FNAME)

    problems = []
    for word in sorted(CMU.keys()):
        print word
        pronun = [l.lower() for l in CMU[word][0]]
        v = ViterbiAligner(word,pronun,allowables)
        v.align()
        alignment = v.get_best_path()
        if not len(alignment):
            problems.append((word,pronun,v))

    try:
        with open('alignment_probabilities.pickle') as f:
            alignment_probabilities = pickle.load(f)
    except:
        em = ViterbiEM(CMU, allowables)
        em.run_EM()
        alignment_probabilities = em.alignment_probabilities[-1]

        with open('alignment_probabilities.pickle','w') as fout:
            pickle.dump(alignment_probabilities,fout)

    try:
        with open('alignments.pickle') as f:
            alignments = pickle.load(f)
    except:
        alignments = []
        for word in sorted(CMU.keys()):
            pronun = [l.lower() for l in CMU[word][0]]
            v = ViterbiAligner(word,pronun,alignment_probabilities)
            v.align()
            alignment = v.get_best_path()
            if not len(alignment):
                print "no alignment for",word,pronun
            alignments.append(alignment)
        with open('alignments.pickle','w') as fout:
            pickle.dump(alignments,fout)

    try:
        with open('features_targets.pickle') as f:
            all_features,all_targets = pickle.load(f)
    except:
        letter_dict, phone_dict = build_int_translators(alignment_probabilities)

        all_features = []
        all_targets = []
        for alignment in alignments:
            features,targets = build_features(alignment, letter_dict, phone_dict)

            all_features += features
            all_targets += targets
        with open('features_targets.pickle','w') as fout:
            pickle.dump((all_features,all_targets),fout)
    '''
    from sklearn import tree
    from sklearn import preprocessing
    from sklearn.cross_validation import cross_val_score
    import numpy as np

    try:
        with open('features_targets_enc.pickle') as f:
            feature_enc,target_array = pickle.load(f)
    except:
        enc = preprocessing.OneHotEncoder()
        enc.fit(all_features)
        feature_enc = enc.transform(all_features)
        target_array = np.array(all_targets)
        with open('features_targets_enc.pickle','w') as fout:
            pickle.dump((feature_enc,target_array),fout)

    # real stuff is below. this is testing for max_depth
    # NOTE: the unconstrained tree gives max depth 94
    # so we'll go up to 90 and then try unconstrained

    feature_array = feature_enc.toarray()
    print "feature array densified"

    fout = open('max_depth_crossval_tests.csv','w')
    fwriter = csv.writer(fout)
    headerout = ['depth','avg'] + range(CROSSVAL_NFOLDS)

    for depth in range(0, 94, DEPTH_TEST_STEP)[1:]:
        print "depth =", depth
        clf = tree.DecisionTreeClassifier(max_depth=depth)
        accuracies = cross_val_score(clf,
                                     feature_array,
                                     target_array,
                                     cv=10)
        avg_acc = np.mean(accuracies)
        acc_list = list(accuracies)
        rowout = [depth, avg_acc] + acc_list
        fwriter.writerow(rowout)

        print "accuracy=", avg_acc

    '''
    try:
        with open('dtree.pickle') as f:
            clf = pickle.load(f)
    except:
        # convert sparse to dense
        # THIS GETS HUGE
        feature_array = feature_enc.toarray()

        # and fitting this tree takes forever
        clf = tree.DecisionTreeClassifier()
        clf = clf.fit(feature_array, target_array)

    # or do cross-validation

    clf = tree.DecisionTreeClassifier(random_state=0)
    accuracies = cross_val_score(clf, feature_array, target_array, cv=10)
    '''

    ''' some accuracies from a sample run:
    [ 0.80291479,  0.80914104,  0.78321458,  0.80681484,  0.80617996,
        0.7742462 ,  0.78304495,  0.78762121,  0.79670611,  0.82589242]
    '''
