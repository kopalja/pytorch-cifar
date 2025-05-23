'''Train CIFAR10 with PyTorch.'''

import sys
import shutil

import pandas as pd
import torch
torch.manual_seed(0)
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torch.backends.cudnn as cudnn
from torch.utils.tensorboard import SummaryWriter

import torchvision
import torchvision.transforms as transforms

import os
import argparse

from models import *
from utils import progress_bar

from sgd_overshoot import SGDO


# Training
def train(epoch):
    print('\nEpoch: %d' % epoch)
    net.train()
    train_loss = 0
    correct = 0
    total = 0
    for batch_idx, (inputs, targets) in enumerate(trainloader):
        inputs, targets = inputs.to(device), targets.to(device)
        optimizer.zero_grad()
        outputs = net(inputs)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()

        train_loss += loss.item()
        _, predicted = outputs.max(1)
        total += targets.size(0)
        correct += predicted.eq(targets).sum().item()

        progress_bar(batch_idx, len(trainloader), 'Loss: %.3f | Acc: %.3f%% (%d/%d)'
                     % (train_loss/(batch_idx+1), 100.*correct/total, correct, total))
    return train_loss/(batch_idx+1), 100.*correct/total


def test(epoch):
    net.eval()
    if isinstance(optimizer, SGDO):
        optimizer.move_to_base()
    test_loss = 0
    correct = 0
    total = 0
    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(testloader):
            inputs, targets = inputs.to(device), targets.to(device)
            outputs = net(inputs)
            loss = criterion(outputs, targets)

            test_loss += loss.item()
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()

            progress_bar(batch_idx, len(testloader), 'Loss: %.3f | Acc: %.3f%% (%d/%d)'
                         % (test_loss/(batch_idx+1), 100.*correct/total, correct, total))


    if isinstance(optimizer, SGDO):
        optimizer.move_to_overshoot()
    return test_loss/(batch_idx+1), 100.*correct/total


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='PyTorch CIFAR10 Training')
    parser.add_argument('--run_name', type=str, required=True)
    parser.add_argument('--model', type=str, required=True)
    parser.add_argument('--lr', default=0.1, type=float, help='learning rate')
    parser.add_argument('--overshoot', type=float, default=0)
    args = parser.parse_args()


    device = 'cuda' if torch.cuda.is_available() else 'cpu'

    n_runs = 2
    for seed in range(n_runs):
        torch.manual_seed(11 * seed)

        # Setup logs
        base_dir = os.path.join('tensorboard', f"{args.run_name}_overshoot_{args.overshoot}")
        os.makedirs(base_dir, exist_ok=True)
        log_writer = SummaryWriter(log_dir=os.path.join(base_dir, f"version_{seed + 1}"))
        shutil.copy(os.path.abspath(sys.argv[0]), os.path.join(base_dir, "main.py"))

        # Data
        print('==> Preparing data..')
        transform_train = transforms.Compose([
            transforms.RandomCrop(32, padding=4),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
        ])

        transform_test = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
        ])

        trainset = torchvision.datasets.CIFAR10(
            root='./data', train=True, download=True, transform=transform_train)
        trainloader = torch.utils.data.DataLoader(
            trainset, batch_size=128, shuffle=True, num_workers=2)

        testset = torchvision.datasets.CIFAR10(
            root='./data', train=False, download=True, transform=transform_test)
        testloader = torch.utils.data.DataLoader(
            testset, batch_size=100, shuffle=False, num_workers=2)

        classes = ('plane', 'car', 'bird', 'cat', 'deer',
                'dog', 'frog', 'horse', 'ship', 'truck')

        
        # Model
        print('==> Building model..')
        if args.model == 'vgg':
            net = VGG('VGG19')
        elif args.model == 'resnet':
            print("Using resnet")
            net = ResNet18()
        elif args.model == 'pre_act_resnet':
            net = PreActResNet18()
        elif args.model == 'googlenet':
            net = GoogLeNet()
        elif args.model == 'densenet':
            net = DenseNet121()
        elif args.model == 'resnex':
            net = ResNeXt29_2x64d()
        elif args.model == 'mobilenet':
            net = MobileNet()
        elif args.model == 'mobilenet_v2':
            net = MobileNetV2()
        elif args.model == 'dpn':
            net = DPN92()
        elif args.model == 'shufflenet':
            net = ShuffleNetG2()
        elif args.model == 'senet':
            net = SENet18()
        elif args.model == 'shufflenet_v2':
            net = ShuffleNetV2(1)
        elif args.model == 'efficientnet':
            net = EfficientNetB0()
        elif args.model == 'regnetx':
            net = RegNetX_200MF()
        elif args.model == 'dla':
            net = SimpleDLA()
        else:
            raise Exception(f"Unsupported model name {args.model}")

        net = net.to(device)
        if device == 'cuda':
            net = torch.nn.DataParallel(net)
            cudnn.benchmark = True

        criterion = nn.CrossEntropyLoss()
        if args.overshoot > 0:
            optimizer = SGDO(net.parameters(), lr=args.lr, momentum=0.9, weight_decay=5e-4, overshoot=args.overshoot)
        else:
            optimizer = optim.SGD(net.parameters(), lr=args.lr, momentum=0.9, weight_decay=5e-4)
            
        epochs = 200
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        stats = []
        for epoch in range(epochs):
            train_loss, train_acc = train(epoch)
            val_loss, val_acc = test(epoch)
            scheduler.step()

            # log stats
            stats.append({"train_loss": train_loss, "train_acc": train_acc, "val_loss": val_loss, "val_acc": val_acc})
            for k, v in stats[-1].items():
                log_writer.add_scalar(k, v, epoch)

        pd.DataFrame(stats).to_csv(os.path.join(log_writer.log_dir, "stats.csv"), index=False)
