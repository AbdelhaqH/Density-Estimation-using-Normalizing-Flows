# -*- coding: utf-8 -*-
"""MNIST_ PFE_2D.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1xGKlbbPY8-BlJXS9nwooVFkgrxzk2fpP

# Normalizing flow |

# Real-NVP | 2D | MNIST

Données
"""

import torch
import torch.utils.data as data 
import torch.nn as nn
import tensorflow as tf
from tensorflow.keras.datasets import mnist
import numpy as np
import matplotlib.pyplot as plt
from torch import distributions

class NumpyDataset(data.Dataset):
    def __init__(self, array):
        super().__init__()
        self.array = array

    def __len__(self):
        return len(self.array)

    def __getitem__(self, index):
        return self.array[index]
        
(X_train, Y_train), (X_test, Y_test) = mnist.load_data()
X_train = tf.keras.utils.normalize(X_train)
X_test = tf.keras.utils.normalize(X_test)

data_slice = 1280*7 #ok avec 128!
X_train = X_train[:data_slice,:]
Y_train = Y_train[:data_slice]
X_test = X_test[:data_slice,:]
Y_test = Y_test[:data_slice]

X_train_ = X_train.reshape(len(X_train),-1)  #(784,128)
X_test_ = X_test.reshape(len(X_train),-1)

train_loader_ = data.DataLoader(NumpyDataset(X_train_), batch_size=64, shuffle=True)
test_loader_ = data.DataLoader(NumpyDataset(X_test_), batch_size=64, shuffle=True)


# Réseau de neurones
class SimpleMLP(nn.Module):
    def __init__(self, input_size, hidden_size, num_hidden_layers, output_size):
        super(SimpleMLP, self).__init__()
        layers = [nn.Linear(input_size, hidden_size)]
        layers.append(nn.ReLU())
        for _ in range(num_hidden_layers - 1):
            layers.append(nn.Linear(hidden_size, hidden_size))
            layers.append(nn.ReLU())
        layers.append(nn.Linear(hidden_size, output_size))
        self.layers = nn.Sequential(*layers)

    def forward(self, x):
        return self.layers(x)

#NVP
class RealNVP(nn.Module):
    def __init__(self, mlp, mask, target_distribution):
        super(RealNVP, self).__init__()
        self.target_distribution = target_distribution
        self.mask = mask
        self.mlp = mlp
        #self.t = torch.nn.ModuleList([mlp])
        #self.s = torch.nn.ModuleList([mlp])
        self.scale_scale = nn.Parameter(torch.zeros(784), requires_grad=True)
        self.shift_scale = nn.Parameter(torch.zeros((64,784)), requires_grad=True)
        self.scale_scale_t = nn.Parameter(torch.zeros(784), requires_grad=True)
        self.shift_scale_t = nn.Parameter(torch.zeros((64,784)), requires_grad=True)
        
    def g(self, z):
        x = z[:,0]
        
        for i in range(len(self.mask)):
          x_masked = x*self.mask[i]

          #On prend les log_gamme et beta
          t = mlp(x_masked) * (1-mask[i])
          log_s = mlp(x_masked) * (1-mask[i])
          log_s = log_s.tanh() * self.scale_scale + self.shift_scale
          
          #log_s = mlp(z_masked) * (1-mask[i])
          #t = mlp(z_masked) * (1-mask[i])
          #log_s = log_s.tanh() * self.scale_scale 
          
          #x = x * torch.exp(log_s) + t
          x = x_masked + (1 - self.mask[i]) * (x * torch.exp(log_s) + t)
        return x

    def f(self, x):
        log_det_J, z = x.new_zeros(x.shape[0]), x

        for i in reversed(range(len(self.mask))):
          z_masked = self.mask[i] * z

          #log_s, t = self.mlp(z_masked).chunk(2, dim=1)
          #log_s = mlp(z_masked) * (1-mask[i])
          #t = mlp(z_masked) * (1-mask[i])
          #log_s = log_s.tanh() * self.scale_scale 

          t = mlp(z_masked) * (1-mask[i])
          log_s = mlp(z_masked) * (1-mask[i])
          log_s = log_s.tanh() * self.scale_scale + self.shift_scale
          
          z = (1 - self.mask[i]) * (z - t) * torch.exp(-log_s) + z_masked
          #z = (z - t) * torch.exp(-log_s)
          log_det_J -= log_s.sum(dim=1)

        return z, log_det_J
    
    def log_prob(self,x):
        z, logp = self.f(x)
        return self.target_distribution.log_prob(z) + logp

    def sample(self, batchSize): 
        z = self.target_distribution.sample((batchSize, 1))
        logp = self.target_distribution.log_prob(z)
        x = self.g(z)
        return x

# Initialiser le réseau de neurones
mlp = SimpleMLP(784, 128, 2, 784)

#Le masque prend la moitié du vecteur de taille 784 qui correspond à une image 
arr = np.zeros(784)
arr[392:] = 1
mask = nn.Parameter(torch.from_numpy(np.array([arr, 1 - arr] * 3).astype(np.float32)), requires_grad=False) #plus j'augmente les couplings layers plus la loss diminue fortement

# Distribution de base
prior_z = distributions.MultivariateNormal(torch.zeros(784), torch.eye(784))

# Initialiser l'objet RealNVP
flow = RealNVP(mlp, mask, prior_z)

device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

optimizer = torch.optim.Adam(flow.parameters(), lr=1e-4)

def train(flow, optimizer, train_loader, num_epochs):
  train_losses, test_losses = [], []
  for epoch in range(num_epochs):
    for x in train_loader_:
      optimizer.zero_grad()
      loss = - flow.log_prob(x.float()).mean()  
      loss.backward(retain_graph=True)
      optimizer.step()
    train_losses.append(loss)
    print(f"Epoch [{epoch+1}/{num_epochs}], Loss: {loss.item():.4f}")
  return train_losses

train_losses = train(flow, optimizer, train_loader_, 10)

losses = []
for i in range(len(train_losses)):
  losses.append(train_losses[i].detach().numpy())

_ = plt.plot(losses, label='train_loss')
#_ = plt.plot(test_losses, label='test_loss')
plt.legend()

x = next(iter(test_loader_)).float()
plt.figure(figsize = (10,10))
bottom = 0.35
for i in range(12):
    plt.subplots_adjust(bottom)
    plt.subplot(4,4,i+1)
    plt.imshow(x[i].reshape(28,28), cmap= plt.cm.binary)

z = []
for x in test_loader_:
  z.append(flow.f(x.float())[0].detach().numpy())
z = np.concatenate(z)

plt.figure(figsize = (10,10))
bottom = 0.35
for i in range(12):
    plt.subplots_adjust(bottom)
    plt.subplot(4,4,i+1)
    plt.imshow(z[i].reshape(28,28), cmap= plt.cm.binary)

z = []
for x in test_loader_:
  z.append(flow.f(x.float())[0].detach().numpy())
z = np.concatenate(z)

plt.figure(figsize = (10,10))
bottom = 0.35
for i in range(12):
    plt.subplots_adjust(bottom)
    plt.subplot(4,4,i+1)
    plt.imshow(z[i].reshape(28,28), cmap= plt.cm.binary)