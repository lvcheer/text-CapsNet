import tensorflow as tf
from tensorflow.contrib import rnn

from utils import get_batch_dataset
from capsLayer import CapsLayer
from config import cfg

epsilon = 1e-9

class CapsNet(object):

	def __init__(self, is_training=True):
		self.graph = tf.Graph()
		with self.graph.as_default():
			if is_training:
				self.X, self.Y = get_batch_dataset(cfg.dataset, cfg.batch_size, cfg.words, cfg.length, cfg.num_threads)

				self.build_arch()
				self.loss()
				self.summary_()

				self.global_step = tf.Variable(0, name='global_step', trainable=False)
				self.optimizer = tf.train.AdamOptimizer(learning_rate=0.003) #0.003
				self.train_op = self.optimizer.minimize(self.total_loss, global_step=self.global_step)
			else:
				self.X = tf.placeholder(tf.float32, shape=(cfg.batch_size, cfg.length))
				self.Y = tf.placeholder(tf.int32, shape=(cfg.batch_size,))
				self.build_arch()

		tf.logging.info('Setting up...')

	def build_arch(self):
		with tf.variable_scope('Embedding'):
			embed = tf.contrib.layers.embed_sequence(self.X, vocab_size=251969, embed_dim=cfg.embed_dim)

		with tf.variable_scope('Conv1_layer'):
			conv1 = tf.layers.conv1d(embed, filters=cfg.conv1_filters, kernel_size=cfg.conv1_kernel, strides=cfg.conv1_stride, padding=cfg.conv1_padding)

		with tf.variable_scope('First_caps_layer'):
			firstCaps = CapsLayer(num_outputs=cfg.caps1_output, vec_len=cfg.caps1_len, layer_type=cfg.caps1_type, with_routing=cfg.caps1_routing)
			caps1 = firstCaps(conv1, kernel_size=cfg.caps1_kernel, stride=cfg.caps1_stride)

		with tf.variable_scope('Second_caps_layer'):
			secondCaps = CapsLayer(num_outputs=cfg.caps2_output, vec_len=cfg.caps2_len, layer_type='FC', with_routing=cfg.caps2_routing)
			self.caps2 = secondCaps(caps1, kernel_size=3, stride=1)



		with tf.variable_scope('LSTM_layer'):
			caps2_reshape = tf.reshape(self.caps2, [cfg.batch_size, 4, -1])
			caps2_unstack = tf.unstack(caps2_reshape, 4, 1)
			W = tf.Variable(tf.random_normal([32, 4]))
			b = tf.Variable(tf.random_normal([4]))
			lstm_layer = rnn.BasicLSTMCell(32, forget_bias=1)
			outputs, _ = rnn.static_rnn(lstm_layer, caps2_unstack, dtype='float32')
			self.prediction = tf.matmul(outputs[-1], W) + b


		#========================================

		with tf.variable_scope('Out'):
			self.v_j = tf.sqrt(tf.reduce_sum(tf.square(self.caps2), axis=2, keep_dims=True) + epsilon)

		#========================================

	def loss(self):
		self.logits = tf.squeeze(self.v_j)
		self.Y = tf.cast(self.Y, tf.float32)
		self.total_loss = tf.nn.sigmoid_cross_entropy_with_logits(logits=self.prediction, labels=self.Y)
		#self.total_loss = tf.losses.softmax_cross_entropy(onehot_labels=self.Y, logits=self.logits)
		self.total_loss = tf.reduce_mean(self.total_loss)

	def summary_(self):
		train_summary = []
		train_summary.append(tf.summary.scalar('train/total_loss', self.total_loss))
		caps2_weights = tf.reshape(self.caps2, shape=(cfg.batch_size, 4, 16, 1))
		train_summary.append(tf.summary.image('image', caps2_weights))

		#preds = tf.round(tf.squeeze(self.v_j)) XX
		#preds = tf.argmax(tf.squeeze(self.v_j), axis=1)
		#preds = tf.cast(preds, tf.int32)

		preds = tf.argmax(self.prediction, axis=1)

		# Get label from Y
		self.labels = tf.argmax(self.Y, axis=1)

		correct_prediction = tf.equal(tf.to_int32(self.labels), tf.to_int32(preds))
		self.accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

		train_summary.append(tf.summary.scalar('accuracy', self.accuracy))

		self.train_summary = tf.summary.merge(train_summary)