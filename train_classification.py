from __future__ import print_function
import argparse
import sys
sys.path.append("../")
import os
import random
import torch
import torch.nn.parallel
import torch.optim as optim
import torch.utils.data
from pointnet.dataset import ShapeNetDataset, ModelNetDataset
from pointnet.model import PointNetCls, feature_transform_regularizer
import torch.nn.functional as F
from tqdm import tqdm
import datetime

#from torch.utils.tensorboard import SummaryWriter       
#writer = SummaryWriter("runs/pointnettest")

parser = argparse.ArgumentParser()
parser.add_argument(
    '--batchSize', type=int, default=32, help='input batch size')
parser.add_argument(
    '--num_points', type=int, default=2500, help='input batch size')
parser.add_argument(
    '--workers', type=int, help='number of data loading workers', default=4)
parser.add_argument(
    '--nepoch', type=int, default=250, help='number of epochs to train for')
#parser.add_argument('--outf', type=str, default='cls_simple_CPRTW_37_240_tree_1', help='output folder')#存取資料夾
parser.add_argument('--outf', type=str, default='cls_complex_FNP_37_240_1213', help='output folder')#存取資料夾
#parser.add_argument('--outf', type=str, default='cls_simple_CPRW_37_240_tree_1', help='output folder')#存取資料夾
parser.add_argument('--model', type=str, default='', help='model path') 
parser.add_argument('--dataset', type=str, required=True, help="dataset path")
parser.add_argument('--dataset_type', type=str, default='shapenet', help="dataset type shapenet|modelnet40")
parser.add_argument('--feature_transform', action='store_true', help="use feature transform")

opt = parser.parse_args()
print(opt)

#blue = lambda x: '\033[94m' + x + '\033[0m'

opt.manualSeed = random.randint(1, 10000)  # fix seed
print("Random Seed: ", opt.manualSeed)
random.seed(opt.manualSeed)
torch.manual_seed(opt.manualSeed)

if __name__ == "__main__":

    if opt.dataset_type == 'shapenet':
        dataset = ShapeNetDataset(
            root=opt.dataset,
            classification=True,
            npoints=opt.num_points)

        test_dataset = ShapeNetDataset(
            root=opt.dataset,
            classification=True,
            split='test',
            npoints=opt.num_points,
            data_augmentation=False)
    elif opt.dataset_type == 'modelnet40':
        dataset = ModelNetDataset(
            root=opt.dataset,
            npoints=opt.num_points,
            split='train')

        test_dataset = ModelNetDataset(
            root=opt.dataset,
            split='test',
            npoints=opt.num_points,
            data_augmentation=False)
    else:
        exit('wrong dataset type')


    dataloader = torch.utils.data.DataLoader(
        dataset,
        batch_size=opt.batchSize,
        shuffle=True,
        num_workers=int(opt.workers))

    testdataloader = torch.utils.data.DataLoader(
        test_dataset,
        batch_size=opt.batchSize,
        shuffle=True,
        num_workers=int(opt.workers))

    print(len(dataset), len(test_dataset))
    num_classes = len(dataset.classes)
    print('classes', num_classes)

    try:
        os.makedirs(opt.outf)
    except OSError:
        pass

    classifier = PointNetCls(k=num_classes, feature_transform=opt.feature_transform)

    if opt.model != '':
        classifier.load_state_dict(torch.load(opt.model))


    optimizer = optim.Adam(classifier.parameters(), lr=0.001, betas=(0.9, 0.999))
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=20, gamma=0.5)
    classifier.cuda()   #.cuda = 使用GPU運算

    num_batch = len(dataset) / opt.batchSize
    time_start=datetime.datetime.now()
    ss=str(time_start)
    print ("start time:",time_start)
    for epoch in range(opt.nepoch):

        for i, data in enumerate(dataloader, 0):
            # get the inputs input, labels
            points, target = data
            target = target[:, 0]
            points = points.transpose(2, 1)
            points, target = points.cuda(), target.cuda()
            optimizer.zero_grad()
            classifier = classifier.train()
            pred, trans, trans_feat = classifier(points)
            loss = F.nll_loss(pred, target)
            if opt.feature_transform:
                loss += feature_transform_regularizer(trans_feat) * 0.001
            loss.backward()
            optimizer.step()
            pred_choice = pred.data.max(1)[1]
            correct = pred_choice.eq(target.data).cpu().sum()
            print('[%d: %d/%d] train loss: %f accuracy: %f' % (epoch, i, num_batch, loss.item(), correct.item() / float(opt.batchSize)))
           # writer.add_scalar('trainloss',loss.item(),epoch)
            #writer.add_scalar('trainaccuracy',correct.item() / float(opt.batchSize))
            #writer.close()

            if i % 10 == 0:
                j, data = next(enumerate(testdataloader, 0))
                points, target = data
                target = target[:, 0]
                points = points.transpose(2, 1)
                points, target = points.cuda(), target.cuda()
                classifier = classifier.eval()
                pred, _, _ = classifier(points)
                test_loss = F.nll_loss(pred, target)
                pred_choice = pred.data.max(1)[1]
                test_correct = pred_choice.eq(target.data).cpu().sum()
                print('[%d: %d/%d] %s loss: %f accuracy: %f' % (epoch, i, num_batch, 'test', test_loss.item(), test_correct.item()/float(opt.batchSize)))
                #writer.add_scalar('testloss',test_loss.item(),epoch)
                #writer.add_scalar('testaccuracy',test_correct.item()/float(opt.batchSize))
                #writer.close()
        scheduler.step()

        time_end=datetime.datetime.now()
        # sss=str(time_end)
        # print (time_end)
        #time_span_str=str((time_end-time_start))
        torch.save({
            'epoch': epoch, 
            'classifier.state_dict': classifier.state_dict(), 
            'loss': loss.item(),
            'acc': correct.item()/float(opt.batchSize),
            'test_loss': test_loss.item(),
            'test_acc': test_correct.item()/float(opt.batchSize)},
            '%s/cls_model_%d.tar' % (opt.outf, epoch))
            #classifier.state_dict(), '%s/cls_model_%d.pth' % (opt.outf, epoch))

    total_correct = 0
    total_testset = 0
    for i,data in tqdm(enumerate(testdataloader, 0)):
        points, target = data
        target = target[:, 0]
        points = points.transpose(2, 1)
        points, target = points.cuda(), target.cuda()
        classifier = classifier.eval()
        pred, _, _ = classifier(points)
        pred_choice = pred.data.max(1)[1]
        correct = pred_choice.eq(target.data).cpu().sum()
        total_correct += correct.item()
        total_testset += points.size()[0]
    time_span_str=str((time_end-time_start).seconds)
    sss=str(time_end)
    print (time_end)
    print("final accuracy {}".format(total_correct / float(total_testset)) + "\nTrain Time: " + time_span_str + "s")